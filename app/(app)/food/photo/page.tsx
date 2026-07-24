import { PhotoFoodLogger } from "./PhotoFoodLogger";

export default function PhotoFoodPage() {
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <h1 className="font-display text-2xl font-semibold">
        Log food from a photo
      </h1>
      <p className="text-sm text-ink-soft">
        Best for homemade or unpackaged food. AI estimates are a starting
        point — fields flagged low/medium confidence are worth double-checking.
      </p>
      <PhotoFoodLogger />
    </div>
  );
}
