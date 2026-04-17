import { describe, expect, it } from "vitest";

import {
  passwordRequirementChecks,
  passwordStrengthLabel,
  passwordStrengthScore,
} from "./password-rules";

describe("password-rules", () => {
  it("scores all criteria", () => {
    expect(passwordStrengthScore("Aa1!abcd")).toBe(5);
    expect(passwordStrengthLabel(5)).toBe("strong");
  });

  it("detects missing criteria", () => {
    const c = passwordRequirementChecks("short");
    expect(c.minLength).toBe(false);
    expect(c.uppercase).toBe(false);
  });
});
