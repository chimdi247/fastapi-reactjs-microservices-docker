import * as React from "react";
import { toast } from "sonner";
import { X, ImageIcon } from "lucide-react";
import { productsApi, getErrorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Product } from "@/types";

export function EditProductForm({
  product,
  onDone,
  onCancel,
}: {
  product: Product;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = React.useState(product.name);
  const [price, setPrice] = React.useState(String(product.price));
  const [description, setDescription] = React.useState(product.description || "");
  const [imageUrl, setImageUrl] = React.useState(product.image_url || "");
  const [isSaving, setIsSaving] = React.useState(false);
  const [previewFailed, setPreviewFailed] = React.useState(false);

  React.useEffect(() => setPreviewFailed(false), [imageUrl]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await productsApi.update(product.id, {
        name: name.trim(),
        price: Number(price),
        description: description.trim(),
        image_url: imageUrl.trim(),
      });
      toast.success("Product updated");
      onDone();
    } catch (err) {
      toast.error(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="px-6 pb-5 space-y-3 border-t border-border pt-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Editing product</span>
        <button
          type="button"
          onClick={onCancel}
          className="text-muted-foreground hover:text-foreground"
          aria-label="Cancel edit"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`ep-name-${product.id}`} className="text-xs">Name</Label>
        <Input
          id={`ep-name-${product.id}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="h-8 text-sm"
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`ep-price-${product.id}`} className="text-xs">Price ($)</Label>
        <Input
          id={`ep-price-${product.id}`}
          type="number"
          min="0"
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="h-8 text-sm"
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`ep-desc-${product.id}`} className="text-xs">Description</Label>
        <Textarea
          id={`ep-desc-${product.id}`}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor={`ep-img-${product.id}`} className="text-xs">Image URL</Label>
        <Input
          id={`ep-img-${product.id}`}
          value={imageUrl}
          onChange={(e) => setImageUrl(e.target.value)}
          placeholder="https://…"
          className="h-8 text-sm"
        />
      </div>

      {imageUrl.trim() && (
        <div className="h-24 w-full bg-muted rounded-md overflow-hidden flex items-center justify-center">
          {previewFailed ? (
            <ImageIcon className="w-5 h-5 text-muted-foreground" />
          ) : (
            <img
              src={imageUrl}
              alt="Preview"
              className="w-full h-full object-cover"
              onError={() => setPreviewFailed(true)}
            />
          )}
        </div>
      )}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={isSaving}>
          {isSaving ? "Saving…" : "Save changes"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
