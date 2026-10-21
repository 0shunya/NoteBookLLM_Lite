/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as auth from "../auth.js";
import type * as chat from "../chat.js";
import type * as conversations from "../conversations.js";
import type * as documents from "../documents.js";
import type * as geminiKeyActions from "../geminiKeyActions.js";
import type * as http from "../http.js";
import type * as ingestion from "../ingestion.js";
import type * as lib_chunker from "../lib/chunker.js";
import type * as lib_gemini from "../lib/gemini.js";
import type * as lib_identity from "../lib/identity.js";
import type * as lib_supabaseStorage from "../lib/supabaseStorage.js";
import type * as notebooks from "../notebooks.js";
import type * as settings from "../settings.js";
import type * as storage from "../storage.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  auth: typeof auth;
  chat: typeof chat;
  conversations: typeof conversations;
  documents: typeof documents;
  geminiKeyActions: typeof geminiKeyActions;
  http: typeof http;
  ingestion: typeof ingestion;
  "lib/chunker": typeof lib_chunker;
  "lib/gemini": typeof lib_gemini;
  "lib/identity": typeof lib_identity;
  "lib/supabaseStorage": typeof lib_supabaseStorage;
  notebooks: typeof notebooks;
  settings: typeof settings;
  storage: typeof storage;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {
  betterAuth: import("@convex-dev/better-auth/_generated/component.js").ComponentApi<"betterAuth">;
};
