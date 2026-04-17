import { describe, expect, it } from "vitest";

import { normalizeOtp, OTP_LENGTH } from "./otp-utils";

describe("otp-utils", () => {
  it("strips non-digits", () => {
    expect(normalizeOtp("12a3b4")).toBe("1234");
  });

  it("caps at OTP_LENGTH", () => {
    expect(normalizeOtp("1234567890")).toBe("123456");
    expect(normalizeOtp("").length).toBe(0);
  });

  it("OTP_LENGTH is 6 for Supabase signup OTP", () => {
    expect(OTP_LENGTH).toBe(6);
  });
});
