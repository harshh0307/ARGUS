"use client";

import { useState, useRef } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Plus, Upload } from "lucide-react";

interface AddVendorModalProps {
  onVendorAdded?: () => void;
}

export function AddVendorModal({ onVendorAdded }: AddVendorModalProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [specUrl, setSpecUrl] = useState("");
  const [specFile, setSpecFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const autoSlug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      const finalSlug = slug.trim() || autoSlug;
      const result = await api.createVendor({
        name: name.trim(),
        slug: finalSlug || undefined,
        spec_url: specUrl.trim() || undefined,
      });
      if (specFile) {
        await api.uploadSpec(result.slug, specFile);
      }
      toast.success("Vendor created", { description: result.slug });
      setName("");
      setSlug("");
      setSpecUrl("");
      setSpecFile(null);
      setOpen(false);
      onVendorAdded?.();
    } catch (err) {
      toast.error("Failed to create vendor", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="sm" className="gap-1">
          <Plus className="h-3.5 w-3.5" />
          Add Vendor
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-96">
        <SheetTitle>Add Custom Vendor</SheetTitle>
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="v-name">Name</Label>
            <Input
              id="v-name"
              placeholder="e.g. Acme API"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="v-slug">Slug (auto-generated)</Label>
            <Input
              id="v-slug"
              placeholder={autoSlug || "auto-generated"}
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="v-url">Spec URL (optional)</Label>
            <Input
              id="v-url"
              placeholder="https://api.example.com/openapi.json"
              value={specUrl}
              onChange={(e) => setSpecUrl(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Or Upload Spec File</Label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,.yaml,.yml"
              className="hidden"
              onChange={(e) => setSpecFile(e.target.files?.[0] ?? null)}
            />
            <Button
              type="button"
              variant="outline"
              className="w-full gap-2"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="h-3.5 w-3.5" />
              {specFile ? specFile.name : "Choose JSON/YAML file"}
            </Button>
          </div>
          <Button
            type="submit"
            className="w-full"
            disabled={loading || !name.trim()}
          >
            {loading ? "Creating..." : "Create Vendor"}
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
