"use client";

import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import { Upload, FileCheck, Loader2, Pencil } from "lucide-react";
import type { VendorOut, SpecUploadOut } from "@/lib/types";

interface EditVendorModalProps {
  vendor: VendorOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onVendorUpdated?: () => void;
}

export function EditVendorModal({
  vendor,
  open,
  onOpenChange,
  onVendorUpdated,
}: EditVendorModalProps) {
  const [name, setName] = useState(vendor.name);
  const [specFile, setSpecFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<SpecUploadOut | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setName(vendor.name);
      setSpecFile(null);
      setUploadResult(null);
    }
  }, [open, vendor.name]);

  const handleSaveName = async () => {
    if (!name.trim() || name === vendor.name) return;
    setSaving(true);
    try {
      await api.updateVendor(vendor.slug, { name: name.trim() });
      toast.success("Vendor updated");
      onVendorUpdated?.();
    } catch (err) {
      toast.error("Failed to update vendor", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleUploadSpec = async () => {
    if (!specFile) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const result = await api.uploadSpec(vendor.slug, specFile);
      setUploadResult(result);
      toast.success("Spec uploaded", {
        description: `OpenAPI ${result.openapi_version} (${result.format}) — detection ${result.detection_dispatched ? "triggered" : "skipped"}`,
      });
      setSpecFile(null);
      onVendorUpdated?.();
    } catch (err) {
      toast.error("Failed to upload spec", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setUploading(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-96">
        <SheetTitle className="flex items-center gap-2">
          <Pencil className="h-4 w-4" />
          Edit Vendor
        </SheetTitle>

        <div className="mt-6 space-y-6">
          {/* Vendor info */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-[10px]">
                {vendor.slug}
              </Badge>
              <Badge variant="outline" className="text-[10px]">
                {vendor.spec_source === "uploaded" ? "Uploaded" : "Remote"}
              </Badge>
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-name">Name</Label>
              <div className="flex gap-2">
                <Input
                  id="edit-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="flex-1"
                />
                <Button
                  size="sm"
                  onClick={handleSaveName}
                  disabled={saving || !name.trim() || name === vendor.name}
                >
                  {saving ? "Saving..." : "Save"}
                </Button>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-[var(--muted-foreground)]">Spec URL</Label>
              <p className="text-xs text-[var(--foreground)] break-all font-mono">
                {vendor.spec_url}
              </p>
            </div>
          </div>

          {/* Upload spec section */}
          <div className="border-t border-[var(--border)] pt-4 space-y-3">
            <Label>Replace Spec File</Label>
            <p className="text-[10px] text-[var(--muted-foreground)]">
              Upload a new OpenAPI JSON or YAML file to replace the current spec.
              Detection will run automatically after upload.
            </p>

            <input
              ref={fileInputRef}
              type="file"
              accept=".json,.yaml,.yml"
              className="hidden"
              onChange={(e) => {
                setSpecFile(e.target.files?.[0] ?? null);
                setUploadResult(null);
              }}
            />

            <Button
              type="button"
              variant="outline"
              className="w-full gap-2"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Upload className="h-3.5 w-3.5" />
              {specFile ? specFile.name : "Choose JSON/YAML file"}
            </Button>

            {specFile && (
              <Button
                className="w-full gap-2"
                onClick={handleUploadSpec}
                disabled={uploading}
              >
                {uploading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Uploading &amp; validating...
                  </>
                ) : (
                  <>
                    <Upload className="h-3.5 w-3.5" />
                    Upload &amp; Run Detection
                  </>
                )}
              </Button>
            )}

            {uploadResult && (
              <div className="rounded-md bg-[var(--passed)]/10 border border-[var(--passed)]/20 p-3 space-y-1">
                <div className="flex items-center gap-2 text-[var(--passed)]">
                  <FileCheck className="h-4 w-4" />
                  <span className="text-xs font-medium">Spec uploaded successfully</span>
                </div>
                <p className="text-[10px] text-[var(--muted-foreground)]">
                  OpenAPI {uploadResult.openapi_version} ({uploadResult.format}) —{" "}
                  {uploadResult.size.toLocaleString()} bytes
                </p>
                <p className="text-[10px] text-[var(--muted-foreground)]">
                  Detection {uploadResult.detection_dispatched ? "triggered" : "skipped (no change detected)"}
                </p>
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
