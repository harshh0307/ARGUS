"use client";

import { useState, useRef } from "react";
import { useAuth } from "@/providers/auth-provider";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { toast } from "sonner";
import { Upload, FileCheck, Loader2, ArrowRight, SkipForward, CheckCircle2 } from "lucide-react";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);

  // Step 1 — account
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Step 2 — vendor
  const [vendorName, setVendorName] = useState("");
  const [specFile, setSpecFile] = useState<File | null>(null);
  const [vendorLoading, setVendorLoading] = useState(false);
  const [vendorResult, setVendorResult] = useState<{ slug: string; upload?: { openapi_version: string; format: string } } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(email, password, tenantId || undefined);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleVendorSubmit = async () => {
    if (!vendorName.trim()) return;
    setVendorLoading(true);
    try {
      const slug = vendorName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_|_$/g, "");

      const result = await api.createVendor({
        name: vendorName.trim(),
        slug,
      });

      let uploadResult;
      if (specFile) {
        uploadResult = await api.uploadSpec(result.slug, specFile);
      }

      setVendorResult({
        slug: result.slug,
        upload: uploadResult
          ? { openapi_version: uploadResult.openapi_version, format: uploadResult.format }
          : undefined,
      });

      toast.success("Vendor created", { description: result.slug });

      setTimeout(() => router.push("/"), 1500);
    } catch (err) {
      toast.error("Failed to create vendor", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setVendorLoading(false);
    }
  };

  const handleSkip = () => {
    router.push("/");
  };

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-md space-y-6 rounded-xl border border-[var(--border)] bg-[var(--card)] p-8">
        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2">
          <div className={`flex items-center gap-1.5 text-xs font-medium ${step === 1 ? "text-[var(--primary)]" : "text-[var(--passed)]"}`}>
            {step === 2 ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--primary)] text-[10px] text-[var(--primary-foreground)]">1</span>
            )}
            Account
          </div>
          <div className="h-px w-8 bg-[var(--border)]" />
          <div className={`flex items-center gap-1.5 text-xs font-medium ${step === 2 ? "text-[var(--primary)]" : "text-[var(--muted-foreground)]"}`}>
            <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] ${step === 2 ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "bg-[var(--surface)] text-[var(--muted-foreground)]"}`}>2</span>
            First Vendor
          </div>
        </div>

        {/* Step 1 — Account Details */}
        {step === 1 && (
          <>
            <div className="text-center">
              <h1 className="text-2xl font-bold">Create an account</h1>
              <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                Join Argus to monitor API changes
              </p>
            </div>
            <form onSubmit={handleAccountSubmit} className="space-y-4">
              {error && (
                <div className="rounded-md bg-red-500/10 px-4 py-3 text-sm text-red-400">
                  {error}
                </div>
              )}
              <div>
                <label htmlFor="email" className="mb-1 block text-sm font-medium text-[var(--foreground)]">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-[var(--ring)] focus:ring-1 focus:ring-[var(--ring)]"
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <label htmlFor="password" className="mb-1 block text-sm font-medium text-[var(--foreground)]">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-[var(--ring)] focus:ring-1 focus:ring-[var(--ring)]"
                  placeholder="••••••••"
                />
              </div>
              <div>
                <label htmlFor="tenant" className="mb-1 block text-sm font-medium text-[var(--foreground)]">
                  Team / Organization <span className="text-[var(--muted-foreground)]">(optional)</span>
                </label>
                <input
                  id="tenant"
                  type="text"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-[var(--ring)] focus:ring-1 focus:ring-[var(--ring)]"
                  placeholder="my-team"
                />
                <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                  Leave blank to use your email prefix as team ID
                </p>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-md bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50"
              >
                {loading ? "Creating account..." : "Continue"}
              </button>
            </form>
          </>
        )}

        {/* Step 2 — First Vendor (optional) */}
        {step === 2 && !vendorResult && (
          <>
            <div className="text-center">
              <h1 className="text-2xl font-bold">Set up your first vendor</h1>
              <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                Add an API to monitor, or skip and do it later from the dashboard.
              </p>
            </div>
            <div className="space-y-4">
              <div>
                <label htmlFor="vendor-name" className="mb-1 block text-sm font-medium text-[var(--foreground)]">
                  Vendor name
                </label>
                <input
                  id="vendor-name"
                  type="text"
                  value={vendorName}
                  onChange={(e) => setVendorName(e.target.value)}
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm outline-none focus:border-[var(--ring)] focus:ring-1 focus:ring-[var(--ring)]"
                  placeholder="e.g. Acme API"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-[var(--foreground)]">
                  OpenAPI spec <span className="text-[var(--muted-foreground)]">(optional)</span>
                </label>
                <p className="text-[10px] text-[var(--muted-foreground)]">
                  Upload a JSON or YAML OpenAPI spec file. You can add this later.
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.yaml,.yml"
                  className="hidden"
                  onChange={(e) => setSpecFile(e.target.files?.[0] ?? null)}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm text-[var(--muted-foreground)] hover:border-[var(--ring)] hover:text-[var(--foreground)] transition-colors"
                >
                  <Upload className="h-4 w-4" />
                  {specFile ? specFile.name : "Choose JSON/YAML file"}
                </button>
                {specFile && (
                  <div className="flex items-center gap-2 text-xs text-[var(--passed)]">
                    <FileCheck className="h-3.5 w-3.5" />
                    {specFile.name} ({(specFile.size / 1024).toFixed(1)} KB)
                  </div>
                )}
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleSkip}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-md border border-[var(--border)] px-4 py-2 text-sm text-[var(--muted-foreground)] hover:bg-[var(--surface)] transition-colors"
                >
                  <SkipForward className="h-3.5 w-3.5" />
                  Skip for now
                </button>
                <button
                  onClick={handleVendorSubmit}
                  disabled={vendorLoading || !vendorName.trim()}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-md bg-[var(--primary)] px-4 py-2 text-sm font-medium text-[var(--primary-foreground)] hover:opacity-90 disabled:opacity-50"
                >
                  {vendorLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Setting up...
                    </>
                  ) : (
                    <>
                      Complete Setup
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </>
        )}

        {/* Step 2 — Success */}
        {step === 2 && vendorResult && (
          <div className="text-center space-y-4">
            <CheckCircle2 className="h-12 w-12 text-[var(--passed)] mx-auto" />
            <div>
              <h1 className="text-2xl font-bold">You&apos;re all set!</h1>
              <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                Vendor <span className="font-medium text-[var(--foreground)]">{vendorResult.slug}</span> created
                {vendorResult.upload && (
                  <> with OpenAPI {vendorResult.upload.openapi_version} ({vendorResult.upload.format})</>
                )}.
              </p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                Redirecting to dashboard...
              </p>
            </div>
          </div>
        )}

        {step === 1 && (
          <p className="text-center text-sm text-[var(--muted-foreground)]">
            Already have an account?{" "}
            <Link href="/login" className="text-[var(--primary)] hover:underline">
              Sign in
            </Link>
          </p>
        )}
      </div>
    </div>
  );
}
