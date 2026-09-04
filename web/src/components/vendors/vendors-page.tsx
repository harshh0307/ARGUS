"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/use-polling";
import { POLL_INTERVALS } from "@/lib/constants";
import { AddVendorModal } from "./add-vendor-modal";
import { EditVendorModal } from "./edit-vendor-modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { StaggerContainer, StaggerItem } from "@/components/ui/motion";
import { toast } from "sonner";
import { Trash2, ExternalLink, ToggleLeft, ToggleRight, Pencil, Globe, FileText } from "lucide-react";
import type { VendorOut } from "@/lib/types";

export function VendorsPage() {
  const fetcher = useCallback(() => api.vendors(), []);
  const { data: vendors, isLoading, refresh } = usePolling<VendorOut[]>(
    fetcher,
    POLL_INTERVALS.vendors
  );
  const [deleting, setDeleting] = useState<string | null>(null);
  const [editingVendor, setEditingVendor] = useState<VendorOut | null>(null);

  const handleDelete = async (slug: string) => {
    if (!confirm(`Delete vendor "${slug}"?`)) return;
    setDeleting(slug);
    try {
      await api.deleteVendor(slug);
      toast.success("Vendor deleted");
      refresh();
    } catch (err) {
      toast.error("Failed to delete vendor", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setDeleting(null);
    }
  };

  const handleToggle = async (vendor: VendorOut) => {
    try {
      await api.updateVendor(vendor.slug, {
        name: vendor.name,
        enabled: !vendor.enabled,
      });
      toast.success(`Vendor ${vendor.enabled ? "disabled" : "enabled"}`);
      refresh();
    } catch (err) {
      toast.error("Failed to update vendor", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const vendorList = vendors ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Vendors</h2>
          <p className="text-xs text-[var(--muted-foreground)]">
            Manage API vendors Argus monitors for breaking changes
          </p>
        </div>
        <AddVendorModal onVendorAdded={refresh} />
      </div>

      <ScrollArea className="h-[calc(100vh-220px)]">
        <StaggerContainer className="space-y-3 pr-4">
          {vendorList.map((v) => (
            <StaggerItem key={v.slug}>
              <div className="flex items-center justify-between p-4 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:shadow-md transition-shadow">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{v.name}</span>
                      <Badge variant="outline" className="text-[10px]">
                        {v.slug}
                      </Badge>
                      {!v.enabled && (
                        <Badge variant="outline" className="text-[10px] text-[var(--muted-foreground)]">
                          Disabled
                        </Badge>
                      )}
                      {v.is_custom ? (
                        <Badge variant="outline" className="text-[10px] bg-[var(--agent)]/10 text-[var(--agent)]">
                          Custom
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] text-[var(--muted-foreground)]">
                          Built-in
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      {v.spec_source === "uploaded" ? (
                        <FileText className="h-3 w-3 text-[var(--passed)]" />
                      ) : (
                        <Globe className="h-3 w-3 text-[var(--muted-foreground)]" />
                      )}
                      <p className="text-[10px] text-[var(--muted-foreground)] truncate max-w-md">
                        {v.spec_url}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {v.spec_source === "remote" && (
                    <a
                      href={v.spec_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded-md hover:bg-[var(--surface)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
                      title="Open spec URL"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                  {v.is_custom && (
                    <button
                      onClick={() => setEditingVendor(v)}
                      className="p-1.5 rounded-md hover:bg-[var(--surface)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
                      title="Edit vendor"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => handleToggle(v)}
                    className="p-1.5 rounded-md hover:bg-[var(--surface)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
                    title={v.enabled ? "Disable" : "Enable"}
                  >
                    {v.enabled ? (
                      <ToggleRight className="h-4 w-4 text-[var(--passed)]" />
                    ) : (
                      <ToggleLeft className="h-4 w-4" />
                    )}
                  </button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-[var(--muted-foreground)] hover:text-[var(--breaking)]"
                    onClick={() => handleDelete(v.slug)}
                    disabled={deleting === v.slug}
                    title="Delete vendor"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </StaggerItem>
          ))}
          {vendorList.length === 0 && (
            <p className="text-center text-sm text-[var(--muted-foreground)] py-12">
              No vendors configured
            </p>
          )}
        </StaggerContainer>
      </ScrollArea>

      {editingVendor && (
        <EditVendorModal
          vendor={editingVendor}
          open={!!editingVendor}
          onOpenChange={(o) => { if (!o) setEditingVendor(null); }}
          onVendorUpdated={refresh}
        />
      )}
    </div>
  );
}
