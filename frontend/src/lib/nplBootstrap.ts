/**
 * Shared NPL master-data fetch — deduped in-flight requests + sessionStorage cache.
 */
import api from "@/lib/api";
import { readSessionBootstrap, writeSessionBootstrap, BOOTSTRAP_TTL_MS } from "@/lib/bootstrapCache";

const KEY_BOOTSTRAP = "npl:combined-bootstrap-v3";

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

export type NplBootstrapData = {
  categories: string[];
  cities: string[];
  earliest_launch_date: string;
  products: NplProductRow[];
};

let bootstrapInflight: Promise<NplBootstrapData> | null = null;
const productsByCategory = new Map<string, Promise<string[]>>();

export function peekNplContext(): NplContextData | null {
  const cached = readSessionBootstrap<NplBootstrapData>(KEY_BOOTSTRAP, 1_800_000);
  if (!cached) return null;
  return {
    categories: cached.categories,
    cities: cached.cities,
    earliest_launch_date: cached.earliest_launch_date,
  };
}

export function peekNplBootstrap(): NplBootstrapData | null {
  return readSessionBootstrap<NplBootstrapData>(KEY_BOOTSTRAP, 1_800_000);
}

export async function loadNplBootstrap(options?: { force?: boolean }): Promise<NplBootstrapData> {
  if (!options?.force) {
    const cached = readSessionBootstrap<NplBootstrapData>(KEY_BOOTSTRAP, 1_800_000);
    if (cached) return cached;
  }
  if (!bootstrapInflight) {
    bootstrapInflight = api
      .get<NplBootstrapData>("/api/new-product-launch/bootstrap")
      .then(({ data }) => {
        writeSessionBootstrap(KEY_BOOTSTRAP, data);
        return data;
      })
      .finally(() => {
        bootstrapInflight = null;
      });
  }
  return bootstrapInflight;
}

export async function loadNplContext(options?: { force?: boolean }): Promise<NplContextData> {
  const data = await loadNplBootstrap(options);
  return {
    categories: data.categories,
    cities: data.cities,
    earliest_launch_date: data.earliest_launch_date,
  };
}

export async function loadNplProductIds(): Promise<NplProductRow[]> {
  const data = await loadNplBootstrap();
  return data.products || [];
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
  await loadNplBootstrap();
}
