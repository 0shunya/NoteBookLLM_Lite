import posthog from "posthog-js";

const projectKey = import.meta.env.VITE_POSTHOG_KEY;
let started = false;

if (projectKey) {
  posthog.init(projectKey, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com",
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    person_profiles: "identified_only",
  });
  started = true;
}

export function track(event: string, properties: Record<string, number | boolean> = {}) {
  if (started) posthog.capture(event, properties);
}
