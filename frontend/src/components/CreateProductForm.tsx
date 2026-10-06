import * as React from "react";
import { toast } from "sonner";
import { Plus, X, ImageIcon } from "lucide-react";
import { productsApi, getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export function CreateProductForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState("");
  const [price, setPrice] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [imageUrl, setImageUrl] = React.useState("");
  const [initialStock, setInitialStock] = React.useState("0");
  const [isSaving, setIsSaving] = React.useState(false);
  const [previewFailed, setPreviewFailed] = React.useState(false);

  React.useEffect(() => setPreviewFailed(false), [imageUrl]);

  const reset = () => {
    setName("");
    setPrice("");
    setDescription("");
    setImageUrl("");
    setInitialStock("0");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await productsApi.create({
        name: name.trim(),
        price: Number(price),
        description: description.trim(),
        image_url: imageUrl.trim(),
        initial_stock: Number(initialStock),
      });
      toast.success(`"${name.trim()}" created`);
      reset();
      setOpen(false);
      onCreated();
    } catch (err) {
      // Includes the server's explanation if the cross-service write
      // partially failed — worth showing in full rather than a generic
      // "something went wrong".
      toast.error(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)} className="mb-4">
        <Plus className="w-4 h-4 mr-1.5" />
        New product
      </Button>
    );
  }

  return (
    <Card className="mb-6">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle className="text-base">New product</CardTitle>
            <CardDescription>
              Creates the product and its initial stock level together.
            </CardDescription>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              reset();
            }}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Cancel"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="np-name">Name</Label>
              <Input
                id="np-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Mechanical Keyboard"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="np-price">Price ($)</Label>
              <Input
                id="np-price"
                type="number"
                min="0"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="129.99"
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="np-desc">Description</Label>
            <Textarea
              id="np-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What makes this product worth buying?"
              rows={2}
            />
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="np-img">Image URL</Label>
              <Input
                id="np-img"
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                placeholder="https://…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="np-stock">Initial stock</Label>
              <Input
                id="np-stock"
                type="number"
                min="0"
                step="1"
                value={initialStock}
                onChange={(e) => setInitialStock(e.target.value)}
                required
              />
            </div>
          </div>

          {imageUrl.trim() && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Preview</Label>
              <div className="h-32 w-full bg-muted rounded-lg overflow-hidden flex items-center justify-center">
                {previewFailed ? (
                  <div className="flex flex-col items-center gap-1 text-muted-foreground">
                    <ImageIcon className="w-6 h-6" />
                    <span className="text-xs">Couldn't load that URL</span>
                  </div>
                ) : (
                  <img
                    src={imageUrl}
                    alt="Preview"
                    className="w-full h-full object-cover"
                    onError={() => setPreviewFailed(true)}
                  />
                )}
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <Button type="submit" disabled={isSaving}>
              {isSaving ? "Creating…" : "Create product"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setOpen(false);
                reset();
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
