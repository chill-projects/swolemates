"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

export async function generateInvite() {
  const supabase = await createClient();

  const { error } = await supabase.rpc("create_partner_invite");

  if (error) {
    throw new Error(error.message);
  }

  revalidatePath("/partner");
}
