"use client";

import { useState } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus } from "lucide-react";
import { useVendors } from "@/hooks/use-vendors";

interface AddRepoModalProps {
  onRepoAdded?: () => void;
}

export function AddRepoModal({ onRepoAdded }: AddRepoModalProps) {
  const [open, setOpen] = useState(false);
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [vendorSlug, setVendorSlug] = useState("github");
  const [defaultBranch, setDefaultBranch] = useState("");
  const [loading, setLoading] = useState(false);
  const { vendors } = useVendors();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner.trim() || !name.trim()) return;
    setLoading(true);
    try {
      const result = await api.registerRepository({
        owner: owner.trim(),
        name: name.trim(),
        vendor_slug: vendorSlug,
        default_branch: defaultBranch.trim() || undefined,
      });
      toast.success("Repository added", {
        description: `${owner.trim()}/${name.trim()} — pipeline started`,
      });
      setOwner("");
      setName("");
      setDefaultBranch("");
      setOpen(false);
      onRepoAdded?.();
    } catch (err) {
      toast.error("Failed to add repository", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          size="sm"
          className="h-7 gap-1 text-xs bg-[var(--agent)] hover:bg-[var(--agent)]/90 text-white"
        >
          <Plus className="h-3 w-3" />
          Add Repository
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-96">
        <SheetTitle>Add Repository</SheetTitle>
        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div className="space-y-2">
            <Label htmlFor="owner">Owner / Organization</Label>
            <Input
              id="owner"
              placeholder="e.g. harshh0307"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="name">Repository Name</Label>
            <Input
              id="name"
              placeholder="e.g. argus-demo"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Vendor</Label>
            <Select value={vendorSlug} onValueChange={setVendorSlug}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {vendors.map((v) => (
                  <SelectItem key={v.slug} value={v.slug}>
                    {v.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="branch">Default Branch (optional)</Label>
            <Input
              id="branch"
              placeholder="e.g. main"
              value={defaultBranch}
              onChange={(e) => setDefaultBranch(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            className="w-full"
            disabled={loading || !owner.trim() || !name.trim()}
          >
            {loading ? "Adding..." : "Add & Start Pipeline"}
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}
