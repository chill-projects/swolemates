export type FoodProduct = {
  barcode: string;
  name: string;
  brand: string | null;
  servingSize: string | null;
  caloriesPer100g: number | null;
  proteinPer100g: number | null;
  carbsPer100g: number | null;
  fatPer100g: number | null;
  fiberPer100g: number | null;
};

type OffHit = {
  code?: string;
  product_name?: string;
  product_name_en?: string;
  brands?: string[];
  serving_size?: string;
  nutriments?: {
    ["energy-kcal_100g"]?: number;
    proteins_100g?: number;
    carbohydrates_100g?: number;
    fat_100g?: number;
    fiber_100g?: number;
  };
};

function normalize(hit: OffHit): FoodProduct | null {
  const name = hit.product_name || hit.product_name_en;
  if (!hit.code || !name) return null;

  return {
    barcode: hit.code,
    name,
    brand: hit.brands?.[0] ?? null,
    servingSize: hit.serving_size ?? null,
    caloriesPer100g: hit.nutriments?.["energy-kcal_100g"] ?? null,
    proteinPer100g: hit.nutriments?.proteins_100g ?? null,
    carbsPer100g: hit.nutriments?.carbohydrates_100g ?? null,
    fatPer100g: hit.nutriments?.fat_100g ?? null,
    fiberPer100g: hit.nutriments?.fiber_100g ?? null,
  };
}

// Open Food Facts' legacy cgi/search.pl endpoint is being phased out (returns
// intermittent 503s) — search.openfoodfacts.org is their current
// Elasticsearch-backed search service ("search-a-licious").
export async function searchFoodProducts(query: string): Promise<FoodProduct[]> {
  const url = new URL("https://search.openfoodfacts.org/search");
  url.searchParams.set("q", query);
  url.searchParams.set("page_size", "20");

  const response = await fetch(url, {
    headers: { "User-Agent": "swolemates - personal use" },
  });

  if (!response.ok) {
    throw new Error(`Open Food Facts search failed (${response.status})`);
  }

  const data: { hits?: OffHit[] } = await response.json();

  return (data.hits ?? [])
    .map(normalize)
    .filter((p): p is FoodProduct => p !== null && p.caloriesPer100g !== null);
}
