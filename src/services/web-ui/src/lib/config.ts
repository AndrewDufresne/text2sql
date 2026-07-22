// Pilot user context. Mirrors the env vars passed into the container so the
// web-ui matches Chainlit's behaviour until SSO lands (M7).
import type { UserCtx, UserRole } from "./types";

export const PILOT_USER: UserCtx = {
  id: process.env.NEXT_PUBLIC_PILOT_USER_ID || "alice@bank",
  role: (process.env.NEXT_PUBLIC_PILOT_USER_ROLE as UserRole) || "RM",
  business_unit: process.env.NEXT_PUBLIC_PILOT_BUSINESS_UNIT || "CIB-APAC",
};

export const PRODUCT_NAME = "CIB Text-to-SQL Assistant";
export const PRODUCT_TAGLINE = "Ask CIB data in plain language. Governed. Audited.";
export const PRODUCT_VERSION =
  process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0-rc1";
