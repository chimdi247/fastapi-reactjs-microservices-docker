import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Package } from "lucide-react";
import { ordersApi } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const STATUS_VARIANT: Record<string, "success" | "warning" | "destructive" | "secondary"> = {
  pending: "warning",
  completed: "success",
  failed: "destructive",
};

export default function Orders() {
  const { data: orders, isLoading } = useQuery({
    queryKey: ["orders", "mine"],
    queryFn: ordersApi.mine,
    refetchInterval: 5000,
  });

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight mb-6">My Orders</h1>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !orders || orders.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Package className="w-8 h-8 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">No orders yet — head to Products to place one.</p>
        </div>
      ) : (
        <Card>
          {orders.map((o, i) => (
            <div key={o.id}>
              <div className="flex items-center justify-between px-5 py-4">
                <div>
                  <p className="text-sm font-medium">Order #{o.id}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Product #{o.product_id} · {new Date(o.created_at).toLocaleString()}
                  </p>
                </div>
                <Badge variant={STATUS_VARIANT[o.status] || "secondary"}>{o.status}</Badge>
              </div>
              {i < orders.length - 1 && <Separator />}
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
