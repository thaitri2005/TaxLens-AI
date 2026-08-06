import { NextRequest, NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";
import crypto from "node:crypto";

const apiOrigin = process.env.API_ORIGIN ?? "http://api:8000";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const target = `${apiOrigin.replace(/\/$/, "")}/${path.join("/")}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("content-length");
  headers.delete("x-taxlens-internal-token");
  headers.delete("x-taxlens-user-id");
  headers.delete("x-taxlens-username");
  headers.delete("x-taxlens-role");
  headers.delete("x-taxlens-auth-timestamp");
  headers.delete("x-taxlens-auth-signature");
  const token = await getToken({ req: request, secret: process.env.NEXTAUTH_SECRET });
  if (!token?.sub || !token.role || !token.username || !process.env.AUTH_INTERNAL_TOKEN) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const payload = `${token.sub}:${token.username}:${token.role}:${timestamp}`;
  const signature = crypto.createHmac("sha256", process.env.AUTH_INTERNAL_TOKEN).update(payload).digest("hex");
  headers.set("X-TaxLens-User-Id", token.sub);
  headers.set("X-TaxLens-Username", token.username);
  headers.set("X-TaxLens-Role", token.role);
  headers.set("X-TaxLens-Auth-Timestamp", timestamp);
  headers.set("X-TaxLens-Auth-Signature", signature);

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : new Uint8Array(await request.arrayBuffer());

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");
    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("API proxy request failed", { target, error });
    return NextResponse.json(
      { detail: "The API service could not be reached." },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
