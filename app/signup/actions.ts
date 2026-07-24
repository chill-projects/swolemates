"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export async function signup(formData: FormData) {
  const supabase = await createClient();

  const { data, error } = await supabase.auth.signUp({
    email: formData.get("email") as string,
    password: formData.get("password") as string,
    options: {
      data: {
        display_name: formData.get("displayName") as string,
      },
    },
  });

  if (error) {
    redirect(`/signup?error=${encodeURIComponent(error.message)}`);
  }

  // If email confirmation is required, signUp() creates the user but
  // returns no session — nothing to redirect into yet.
  if (!data.session) {
    redirect("/signup?checkEmail=1");
  }

  redirect("/dashboard");
}
