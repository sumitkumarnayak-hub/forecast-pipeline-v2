/**
 * Shared NPL master-data fetch — deduped in-flight requests + sessionStorage cache.
 */
import api from "@/lib/api";
import { readSessionBootstrap, writeSessionBootstrap, BOOTSTRAP_TTL_MS } from "@/lib/bootstrapCache";

const KEY_CONTEXT = "npl:wizard-context";
const KEY_PRODUCTS = "npl:product-ids";

export type NplContextData = {
  categories: string[];
  cities: string[];
  earliest_launch_date: string;
};

export type NplProductRow = {
  product_id: string;
  product_name: string;
  category: string;
};

let contextInflight: Promise<NplContextData> | null = null;
let productsInflight: Promise<NplProductRow[]> | null = null;
const productsByCategory = new Map<string, Promise<string[]>>();

export function peekNplContext(): NplContextData | null {
  return readSessionBootstrap<NplContextData>(KEY_CONTEXT, BOOTSTRAP_TTL_MS);
}

export async function loadNplContext(options?: { force?: boolean }): Promise<NplContextData> {
  if (!options?.force) {
    const cached = peekNplContext();
    if (cached) return cached;
  }
  if (!contextInflight) {
    contextInflight = api
      .get<NplContextData>("/api/new-product-launch/wizard/context")
      .then(({ data }) => {
        writeSessionBootstrap(KEY_CONTEXT, data);
        return data;
      })
      .finally(() => {
        contextInflight = null;
      });
  }
  return contextInflight;
}

export async function loadNplProductIds(): Promise<NplProductRow[]> {
  const cached = readSessionBootstrap<{ products: NplProductRow[] }>(KEY_PRODUCTS, BOOTSTRAP_TTL_MS);
  if (cached?.products?.length) return cached.products;

  if (!productsInflight) {
    productsInflight = api
      .get<{ products: NplProductRow[] }>("/api/new-product-launch/masters/product-ids")
      .then(({ data }) => {
        const products = data.products || [];
        writeSessionBootstrap(KEY_PRODUCTS, { products });
        return products;
      })
      .finally(() => {
        productsInflight = null;
      });
  }
  return productsInflight;
}

export async function loadNplProductsByCategory(category: string): Promise<string[]> {
  if (!category) return [];
  const existing = productsByCategory.get(category);
  if (existing) return existing;

  const job = api
    .get<{ products: string[] }>("/api/new-product-launch/masters/products", { params: { category } })
    .then(({ data }) => data.products || [])
    .catch(() => [] as string[]);

  productsByCategory.set(category, job);
  return job;
}

export async function prefetchNplBootstrap(): Promise<void> {
  await Promise.allSettled([loadNplContext(), loadNplProductIds()]);
}
