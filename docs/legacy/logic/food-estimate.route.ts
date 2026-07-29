import { GoogleGenAI } from "@google/genai";
import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

const client = new GoogleGenAI({});

const CONFIDENCE_ENUM = ["low", "medium", "high"] as const;

const FOOD_ESTIMATE_SCHEMA = {
  type: "object",
  properties: {
    items: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          serving_description: { type: "string" },
          calories: { type: "number" },
          protein_g: { type: "number" },
          carbs_g: { type: "number" },
          fat_g: { type: "number" },
          fiber_g: { type: "number" },
          confidence: {
            type: "object",
            properties: {
              calories: { type: "string", enum: CONFIDENCE_ENUM },
              protein_g: { type: "string", enum: CONFIDENCE_ENUM },
              carbs_g: { type: "string", enum: CONFIDENCE_ENUM },
              fat_g: { type: "string", enum: CONFIDENCE_ENUM },
              fiber_g: { type: "string", enum: CONFIDENCE_ENUM },
              serving_description: { type: "string", enum: CONFIDENCE_ENUM },
            },
            required: [
              "calories",
              "protein_g",
              "carbs_g",
              "fat_g",
              "fiber_g",
              "serving_description",
            ],
          },
        },
        required: [
          "name",
          "serving_description",
          "calories",
          "protein_g",
          "carbs_g",
          "fat_g",
          "fiber_g",
          "confidence",
        ],
      },
    },
    overall_confidence: { type: "string", enum: CONFIDENCE_ENUM },
    assumptions: { type: "array", items: { type: "string" } },
  },
  required: ["items", "overall_confidence", "assumptions"],
};

export type FoodEstimateItem = {
  name: string;
  serving_description: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  confidence: {
    calories: "low" | "medium" | "high";
    protein_g: "low" | "medium" | "high";
    carbs_g: "low" | "medium" | "high";
    fat_g: "low" | "medium" | "high";
    fiber_g: "low" | "medium" | "high";
    serving_description: "low" | "medium" | "high";
  };
};

export type FoodEstimateResponse = {
  items: FoodEstimateItem[];
  overall_confidence: "low" | "medium" | "high";
  assumptions: string[];
};

export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { imageBase64, mediaType } = await request.json();

  if (!imageBase64 || !mediaType) {
    return NextResponse.json(
      { error: "imageBase64 and mediaType are required" },
      { status: 400 },
    );
  }

  let interaction;
  try {
    interaction = await client.interactions.create({
      model: "gemini-3.5-flash",
      input: [
        {
          type: "text",
          text:
            "Identify each distinct food item in this photo. For each item, estimate " +
            "a reasonable serving size and its calories, protein (g), carbs (g), fat (g), and fiber (g). " +
            "Assign a confidence level (low/medium/high) to EACH field individually — " +
            "low confidence means the estimate could plausibly be off by 30%+ (e.g. hidden oil, " +
            "unclear portion size, ambiguous ingredients); high confidence means a well-known " +
            "item with clear visual cues. List any assumptions you made " +
            "(e.g. 'assumed 1 tbsp of dressing', 'assumed grilled not fried') in assumptions.",
        },
        {
          type: "image",
          data: imageBase64,
          mime_type: mediaType,
        },
      ],
      response_format: {
        type: "text",
        mime_type: "application/json",
        schema: FOOD_ESTIMATE_SCHEMA,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Gemini API request failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }

  if (!interaction.output_text) {
    return NextResponse.json(
      { error: "No estimate returned" },
      { status: 502 },
    );
  }

  const estimate: FoodEstimateResponse = JSON.parse(interaction.output_text);

  return NextResponse.json(estimate);
}
