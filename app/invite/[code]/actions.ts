"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export async function acceptInvite(code: string) {
  const supabase = await createClient();

  const { error } = await supabase.rpc("redeem_partner_invite", {
    invite_code: code,
  });

  if (error) {
    redirect(`/invite/${code}?error=${encodeURIComponent(error.message)}`);
  }

  redirect("/partner");
}
