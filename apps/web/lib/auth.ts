import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

const apiOrigin = process.env.API_ORIGIN ?? "http://api:8000";

export const authOptions: NextAuthOptions = {
  secret: process.env.NEXTAUTH_SECRET,
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "Password",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.username || !credentials.password || !process.env.AUTH_INTERNAL_TOKEN) {
          return null;
        }
        const response = await fetch(`${apiOrigin.replace(/\/$/, "")}/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-TaxLens-Internal-Token": process.env.AUTH_INTERNAL_TOKEN,
          },
          body: JSON.stringify({ username: credentials.username, password: credentials.password }),
          cache: "no-store",
        });
        if (!response.ok) return null;
        return response.json();
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.sub = user.id;
        token.role = user.role;
        token.username = user.username;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.sub ?? "";
        session.user.role = token.role as string;
        session.user.username = token.username as string;
      }
      return session;
    },
  },
};
