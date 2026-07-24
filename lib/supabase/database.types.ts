export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      exercises: {
        Row: {
          created_at: string
          created_by: string | null
          equipment: string | null
          id: string
          is_custom: boolean
          muscle_group: string
          name: string
        }
        Insert: {
          created_at?: string
          created_by?: string | null
          equipment?: string | null
          id?: string
          is_custom?: boolean
          muscle_group: string
          name: string
        }
        Update: {
          created_at?: string
          created_by?: string | null
          equipment?: string | null
          id?: string
          is_custom?: boolean
          muscle_group?: string
          name?: string
        }
        Relationships: [
          {
            foreignKeyName: "exercises_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "exercises_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      food_logs: {
        Row: {
          calories: number
          carbs_g: number
          confidence: Json | null
          created_at: string
          edited_by_user: boolean
          fat_g: number
          fiber_g: number | null
          id: string
          logged_at: string
          meal_type: string | null
          name: string
          photo_storage_path: string | null
          protein_g: number
          raw_ai_response: Json | null
          serving_description: string | null
          source: Database["public"]["Enums"]["food_source"]
          source_ref: string | null
          user_id: string
        }
        Insert: {
          calories: number
          carbs_g: number
          confidence?: Json | null
          created_at?: string
          edited_by_user?: boolean
          fat_g: number
          fiber_g?: number | null
          id?: string
          logged_at?: string
          meal_type?: string | null
          name: string
          photo_storage_path?: string | null
          protein_g: number
          raw_ai_response?: Json | null
          serving_description?: string | null
          source: Database["public"]["Enums"]["food_source"]
          source_ref?: string | null
          user_id: string
        }
        Update: {
          calories?: number
          carbs_g?: number
          confidence?: Json | null
          created_at?: string
          edited_by_user?: boolean
          fat_g?: number
          fiber_g?: number | null
          id?: string
          logged_at?: string
          meal_type?: string | null
          name?: string
          photo_storage_path?: string | null
          protein_g?: number
          raw_ai_response?: Json | null
          serving_description?: string | null
          source?: Database["public"]["Enums"]["food_source"]
          source_ref?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "food_logs_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_logs_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      partner_invites: {
        Row: {
          code: string
          created_at: string
          expires_at: string
          id: string
          inviter_id: string
          redeemed_at: string | null
          redeemed_by: string | null
          status: Database["public"]["Enums"]["invite_status"]
        }
        Insert: {
          code: string
          created_at?: string
          expires_at?: string
          id?: string
          inviter_id: string
          redeemed_at?: string | null
          redeemed_by?: string | null
          status?: Database["public"]["Enums"]["invite_status"]
        }
        Update: {
          code?: string
          created_at?: string
          expires_at?: string
          id?: string
          inviter_id?: string
          redeemed_at?: string | null
          redeemed_by?: string | null
          status?: Database["public"]["Enums"]["invite_status"]
        }
        Relationships: [
          {
            foreignKeyName: "partner_invites_inviter_id_fkey"
            columns: ["inviter_id"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "partner_invites_inviter_id_fkey"
            columns: ["inviter_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "partner_invites_redeemed_by_fkey"
            columns: ["redeemed_by"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "partner_invites_redeemed_by_fkey"
            columns: ["redeemed_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      partner_links: {
        Row: {
          created_at: string
          id: string
          user_id_a: string
          user_id_b: string
        }
        Insert: {
          created_at?: string
          id?: string
          user_id_a: string
          user_id_b: string
        }
        Update: {
          created_at?: string
          id?: string
          user_id_a?: string
          user_id_b?: string
        }
        Relationships: [
          {
            foreignKeyName: "partner_links_user_id_a_fkey"
            columns: ["user_id_a"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "partner_links_user_id_a_fkey"
            columns: ["user_id_a"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "partner_links_user_id_b_fkey"
            columns: ["user_id_b"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "partner_links_user_id_b_fkey"
            columns: ["user_id_b"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          activity_level: Database["public"]["Enums"]["activity_level"] | null
          age: number | null
          avatar_url: string | null
          calorie_target: number | null
          carb_target: number | null
          created_at: string
          current_routine: string | null
          display_name: string
          fat_target: number | null
          fiber_target: number | null
          goal: string | null
          goal_type: Database["public"]["Enums"]["nutrition_goal_type"] | null
          height_in: number | null
          id: string
          onboarding_completed_at: string | null
          protein_target: number | null
          secondary_goal: string | null
          sex: Database["public"]["Enums"]["biological_sex"] | null
          weight_lbs: number | null
        }
        Insert: {
          activity_level?: Database["public"]["Enums"]["activity_level"] | null
          age?: number | null
          avatar_url?: string | null
          calorie_target?: number | null
          carb_target?: number | null
          created_at?: string
          current_routine?: string | null
          display_name: string
          fat_target?: number | null
          fiber_target?: number | null
          goal?: string | null
          goal_type?: Database["public"]["Enums"]["nutrition_goal_type"] | null
          height_in?: number | null
          id: string
          onboarding_completed_at?: string | null
          protein_target?: number | null
          secondary_goal?: string | null
          sex?: Database["public"]["Enums"]["biological_sex"] | null
          weight_lbs?: number | null
        }
        Update: {
          activity_level?: Database["public"]["Enums"]["activity_level"] | null
          age?: number | null
          avatar_url?: string | null
          calorie_target?: number | null
          carb_target?: number | null
          created_at?: string
          current_routine?: string | null
          display_name?: string
          fat_target?: number | null
          fiber_target?: number | null
          goal?: string | null
          goal_type?: Database["public"]["Enums"]["nutrition_goal_type"] | null
          height_in?: number | null
          id?: string
          onboarding_completed_at?: string | null
          protein_target?: number | null
          secondary_goal?: string | null
          sex?: Database["public"]["Enums"]["biological_sex"] | null
          weight_lbs?: number | null
        }
        Relationships: []
      }
      workout_exercises: {
        Row: {
          exercise_id: string
          id: string
          notes: string | null
          order_index: number
          workout_id: string
        }
        Insert: {
          exercise_id: string
          id?: string
          notes?: string | null
          order_index?: number
          workout_id: string
        }
        Update: {
          exercise_id?: string
          id?: string
          notes?: string | null
          order_index?: number
          workout_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "workout_exercises_exercise_id_fkey"
            columns: ["exercise_id"]
            isOneToOne: false
            referencedRelation: "exercises"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "workout_exercises_workout_id_fkey"
            columns: ["workout_id"]
            isOneToOne: false
            referencedRelation: "workouts"
            referencedColumns: ["id"]
          },
        ]
      }
      workout_sets: {
        Row: {
          actual_reps: number | null
          actual_weight: number | null
          completed_at: string
          id: string
          is_warmup: boolean
          prescribed_reps: number | null
          prescribed_weight: number | null
          rest_seconds: number | null
          rpe: number | null
          set_number: number
          set_type: Database["public"]["Enums"]["set_type"]
          work_seconds: number | null
          workout_exercise_id: string
        }
        Insert: {
          actual_reps?: number | null
          actual_weight?: number | null
          completed_at?: string
          id?: string
          is_warmup?: boolean
          prescribed_reps?: number | null
          prescribed_weight?: number | null
          rest_seconds?: number | null
          rpe?: number | null
          set_number: number
          set_type?: Database["public"]["Enums"]["set_type"]
          work_seconds?: number | null
          workout_exercise_id: string
        }
        Update: {
          actual_reps?: number | null
          actual_weight?: number | null
          completed_at?: string
          id?: string
          is_warmup?: boolean
          prescribed_reps?: number | null
          prescribed_weight?: number | null
          rest_seconds?: number | null
          rpe?: number | null
          set_number?: number
          set_type?: Database["public"]["Enums"]["set_type"]
          work_seconds?: number | null
          workout_exercise_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "workout_sets_workout_exercise_id_fkey"
            columns: ["workout_exercise_id"]
            isOneToOne: false
            referencedRelation: "workout_exercises"
            referencedColumns: ["id"]
          },
        ]
      }
      workouts: {
        Row: {
          activity_type: Database["public"]["Enums"]["activity_type"] | null
          completed_at: string | null
          created_at: string
          duration_minutes: number | null
          id: string
          notes: string | null
          started_at: string
          title: string | null
          user_id: string
          workout_type: Database["public"]["Enums"]["workout_type"]
        }
        Insert: {
          activity_type?: Database["public"]["Enums"]["activity_type"] | null
          completed_at?: string | null
          created_at?: string
          duration_minutes?: number | null
          id?: string
          notes?: string | null
          started_at?: string
          title?: string | null
          user_id: string
          workout_type?: Database["public"]["Enums"]["workout_type"]
        }
        Update: {
          activity_type?: Database["public"]["Enums"]["activity_type"] | null
          completed_at?: string | null
          created_at?: string
          duration_minutes?: number | null
          id?: string
          notes?: string | null
          started_at?: string
          title?: string | null
          user_id?: string
          workout_type?: Database["public"]["Enums"]["workout_type"]
        }
        Relationships: [
          {
            foreignKeyName: "workouts_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "partner_profile_public"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "workouts_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      partner_profile_public: {
        Row: {
          avatar_url: string | null
          display_name: string | null
          id: string | null
        }
        Relationships: []
      }
    }
    Functions: {
      create_partner_invite: {
        Args: never
        Returns: {
          code: string
        }[]
      }
      get_invite_preview: {
        Args: { invite_code: string }
        Returns: {
          inviter_display_name: string
          valid: boolean
        }[]
      }
      get_partner_workout_summary: {
        Args: { target_partner_id: string }
        Returns: {
          current_streak_days: number
          last_workout_at: string
          total_workouts: number
          workouts_last_30_days: number
          workouts_last_7_days: number
        }[]
      }
      redeem_partner_invite: {
        Args: { invite_code: string }
        Returns: {
          linked_with: string
        }[]
      }
    }
    Enums: {
      activity_level:
        | "sedentary"
        | "light"
        | "moderate"
        | "active"
        | "very_active"
      activity_type: "yoga" | "pilates" | "cardio" | "other"
      biological_sex: "male" | "female"
      food_source: "barcode" | "text_search" | "photo_ai"
      invite_status: "pending" | "redeemed" | "expired" | "revoked"
      nutrition_goal_type: "lose_weight" | "maintain" | "gain_muscle" | "recomp"
      set_type: "reps" | "time"
      workout_type: "strength" | "activity"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {
      activity_level: [
        "sedentary",
        "light",
        "moderate",
        "active",
        "very_active",
      ],
      activity_type: ["yoga", "pilates", "cardio", "other"],
      biological_sex: ["male", "female"],
      food_source: ["barcode", "text_search", "photo_ai"],
      invite_status: ["pending", "redeemed", "expired", "revoked"],
      nutrition_goal_type: ["lose_weight", "maintain", "gain_muscle", "recomp"],
      set_type: ["reps", "time"],
      workout_type: ["strength", "activity"],
    },
  },
} as const
