import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL");
const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Content-Type": "application/json",
};

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405, headers: corsHeaders });
  }
  if (!supabaseUrl || !anonKey || !serviceRoleKey) {
    console.error("Account deletion function is missing server configuration");
    return Response.json({ error: "Account deletion is not configured" }, { status: 503, headers: corsHeaders });
  }

  const authorization = request.headers.get("Authorization") ?? "";
  const match = authorization.match(/^Bearer\s+([^\s]+)$/i);
  if (!match) {
    return Response.json({ error: "Authentication required" }, { status: 401, headers: corsHeaders });
  }

  // Validate the bearer token as a real Supabase user before using the admin client.
  const callerClient = createClient(supabaseUrl, anonKey, {
    auth: { autoRefreshToken: false, persistSession: false },
    global: { headers: { Authorization: `Bearer ${match[1]}` } },
  });
  const { data: callerResult, error: callerError } = await callerClient.auth.getUser(match[1]);
  if (callerError || !callerResult.user) {
    return Response.json({ error: "Invalid or expired session" }, { status: 401, headers: corsHeaders });
  }

  const adminClient = createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const { error: deletionError } = await adminClient.auth.admin.deleteUser(callerResult.user.id);
  if (deletionError) {
    console.error("Could not delete authenticated caller", deletionError.message);
    return Response.json({ error: "Account deletion failed" }, { status: 500, headers: corsHeaders });
  }

  return Response.json({ deleted: true }, { status: 200, headers: corsHeaders });
});
