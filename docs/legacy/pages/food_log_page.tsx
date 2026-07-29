import Link from "next/link";
import { FoodSearch } from "./FoodSearch";

export default function LogFoodPage() {
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold">Log food</h1>
        <Link
          href="/food/photo"
          className="font-mono text-xs tracking-wide text-teal uppercase"
        >
          Log from a photo →
        </Link>
      </div>
      <FoodSearch />
    </div>
  );
}
