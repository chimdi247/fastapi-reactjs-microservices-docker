import grpc
from concurrent import futures
from sqlmodel import SQLModel, Session, select

import product_pb2
import product_pb2_grpc
from db import engine, get_session
from models import Product

from shared.telemetry import setup_telemetry, instrument_grpc_server

setup_telemetry("product-service")
instrument_grpc_server()


def _to_response(product: Product) -> product_pb2.ProductResponse:
    return product_pb2.ProductResponse(
        id=product.id,
        name=product.name,
        price=product.price,
        description=product.description or "",
        image_url=product.image_url or "",
    )


class ProductService(product_pb2_grpc.ProductServiceServicer):
    def GetProduct(self, request, context):
        print(f"Received request for product ID: {request.id}")

        with Session(engine) as session:
            product = session.get(Product, request.id)

            if product is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Product {request.id} not found")
                return product_pb2.ProductResponse()

            return _to_response(product)

    def ListProducts(self, request, context):
        print("Received request to list all products")

        with Session(engine) as session:
            products = session.exec(select(Product)).all()
            return product_pb2.ListProductsResponse(
                products=[_to_response(p) for p in products]
            )

    def CreateProduct(self, request, context):
        print(f"Received create request for product: {request.name}")

        with Session(engine) as session:
            product = Product(
                name=request.name,
                price=request.price,
                description=request.description or "",
                image_url=request.image_url or "",
            )
            session.add(product)
            session.commit()
            session.refresh(product)

            return _to_response(product)

    def DeleteProduct(self, request, context):
        # Primarily exists so user-service can roll back a half-finished
        # create (product written, inventory write failed) - see its
        # POST /products handler.
        print(f"Received delete request for product ID: {request.id}")

        with Session(engine) as session:
            product = session.get(Product, request.id)

            if product is None:
                return product_pb2.DeleteProductResponse(deleted=False)

            session.delete(product)
            session.commit()
            return product_pb2.DeleteProductResponse(deleted=True)

    def UpdateProduct(self, request, context):
        print(f"Received update request for product ID: {request.id}")

        with Session(engine) as session:
            product = session.get(Product, request.id)

            if product is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Product {request.id} not found")
                return product_pb2.ProductResponse()

            # Only apply fields the caller actually set (proto3 `optional`
            # gives us HasField() presence-tracking) - anything omitted is
            # left as-is on the stored product.
            if request.HasField("name"):
                product.name = request.name
            if request.HasField("price"):
                product.price = request.price
            if request.HasField("description"):
                product.description = request.description
            if request.HasField("image_url"):
                product.image_url = request.image_url

            session.add(product)
            session.commit()
            session.refresh(product)

            return _to_response(product)


def server():
    # Table creation happens here too (idempotent, mirrors what the SQL init
    # scripts under /docker/postgres/init already create) so this service
    # also works standalone against a fresh database.
    SQLModel.metadata.create_all(engine)

    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    product_pb2_grpc.add_ProductServiceServicer_to_server(ProductService(), grpc_server)
    grpc_server.add_insecure_port("[::]:50051")
    grpc_server.start()
    print("Product service (gRPC) listening on :50051")
    grpc_server.wait_for_termination()


if __name__ == "__main__":
    server()
