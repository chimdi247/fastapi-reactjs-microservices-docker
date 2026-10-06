import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShoppingCart, PackageCheck, PackageX, ImageIcon, Pencil, Trash2 } from "lucide-react";
import { productsApi, inventoryApi, ordersApi, getErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { CreateProductForm } from "@/components/CreateProductForm";
import { EditProductForm } from "@/components/EditProductForm";
import type { Product } from "@/types";

function formatMoney(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

export default function Products() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [placingId, setPlacingId] = React.useState<number | null>(null);
  const [editingId, setEditingId] = React.useState<number | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = React.useState<number | null>(null);
  const [deletingId, setDeletingId] = React.useState<number | null>(null);

  const isAdmin = user?.role === "admin";

  const { data: products, isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: productsApi.list,
  });

  const { data: inventory } = useQuery({
    queryKey: ["inventory"],
    queryFn: inventoryApi.list,
  });

  const stockFor = (productId: number) =>
    inventory?.find((i) => i.product_id === productId)?.stock;

  const refreshCatalog = () => {
    queryClient.invalidateQueries({ queryKey: ["products"] });
    queryClient.invalidateQueries({ queryKey: ["inventory"] });
  };

  const handleOrder = async (productId: number) => {
    setPlacingId(productId);
    try {
      await ordersApi.place(productId);
      toast.success("Order placed — check My Orders for status");
      queryClient.invalidateQueries({ queryKey: ["inventory"] });
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setPlacingId(null);
    }
  };

  const handleDelete = async (productId: number) => {
    setDeletingId(productId);
    try {
      await productsApi.remove(productId);
      toast.success("Product deleted");
      refreshCatalog();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setDeletingId(null);
      setConfirmingDeleteId(null);
    }
  };

  return (
    <div>
      {/* Hero banner */}
      <div className="rounded-xl bg-primary text-primary-foreground p-8 mb-8 flex items-center justify-between gap-6 overflow-hidden relative">
        <div className="relative">
          <Badge className="bg-primary-foreground text-primary mb-3">Free shipping this week</Badge>
          <h1 className="text-2xl font-semibold tracking-tight mb-1.5">
            Gear up for your next build
          </h1>
          <p className="text-sm opacity-90 max-w-[46ch]">
            Laptops, keyboards, and monitors — everything here ships from live inventory,
            tracked in real time.
          </p>
        </div>
        <ShoppingCart className="w-16 h-16 opacity-20 shrink-0 hidden sm:block" />
      </div>

      <h2 className="text-lg font-semibold tracking-tight mb-4">Products</h2>

      {isAdmin && <CreateProductForm onCreated={refreshCatalog} />}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !products || products.length === 0 ? (
        <p className="text-sm text-muted-foreground">No products yet.</p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {products.map((p) => {
            const stock = stockFor(p.id);
            const outOfStock = stock === 0;
            const isEditing = editingId === p.id;
            const isConfirmingDelete = confirmingDeleteId === p.id;

            return (
              <Card key={p.id} className="flex flex-col overflow-hidden">
                <ProductImage product={p} />

                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">{p.name}</CardTitle>
                    {stock !== undefined && (
                      <Badge variant={outOfStock ? "destructive" : "success"} className="shrink-0">
                        {outOfStock ? (
                          <PackageX className="w-3 h-3 mr-1" />
                        ) : (
                          <PackageCheck className="w-3 h-3 mr-1" />
                        )}
                        {outOfStock ? "Out of stock" : `${stock} in stock`}
                      </Badge>
                    )}
                  </div>
                  <CardDescription>{p.description}</CardDescription>
                </CardHeader>

                {isAdmin && isEditing && (
                  <EditProductForm
                    product={p}
                    onDone={() => {
                      setEditingId(null);
                      refreshCatalog();
                    }}
                    onCancel={() => setEditingId(null)}
                  />
                )}

                <CardFooter className="mt-auto flex items-center justify-between">
                  <span className="text-lg font-semibold tabular-nums">{formatMoney(p.price)}</span>

                  {isAdmin && isConfirmingDelete ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">Delete this product?</span>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDelete(p.id)}
                        disabled={deletingId === p.id}
                      >
                        {deletingId === p.id ? "Deleting…" : "Confirm"}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setConfirmingDeleteId(null)}>
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {isAdmin && !isEditing && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setEditingId(p.id)}
                            title="Edit product"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setConfirmingDeleteId(p.id)}
                            title="Delete product"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </>
                      )}
                      <Button
                        size="sm"
                        onClick={() => handleOrder(p.id)}
                        disabled={placingId === p.id || outOfStock}
                      >
                        <ShoppingCart className="w-3.5 h-3.5 mr-1.5" />
                        {placingId === p.id ? "Ordering…" : "Order"}
                      </Button>
                    </div>
                  )}
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Product image, with a graceful placeholder if there's no URL or it fails to load. */
function ProductImage({ product }: { product: Product }) {
  const [failed, setFailed] = React.useState(false);

  // Reset the error state if the URL changes (e.g. an admin just fixed it).
  React.useEffect(() => setFailed(false), [product.image_url]);

  if (!product.image_url || failed) {
    return (
      <div className="h-40 bg-muted flex items-center justify-center">
        <ImageIcon className="w-8 h-8 text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="h-40 bg-muted">
      <img
        src={product.image_url}
        alt={product.name}
        className="w-full h-full object-cover"
        onError={() => setFailed(true)}
      />
    </div>
  );
}
