import rubricDocument from "../../contracts/v1/rubric.json";

/**
 * The reviewer rubric, as the backend defines it.
 *
 * `contracts/v1/rubric.json` is generated from `backend/rubric.py` and a backend
 * contract test fails if the two drift, so the 「评分规则」 view can never show
 * a weight the scorer does not use.
 */
export interface RubricDimension {
  id: string;
  label_zh: string;
  label_en: string;
  weight: number;
  focus: string;
}

export interface Rubric {
  rubric_version: string;
  scoring_version: string;
  scale: {
    min: number;
    max: number;
    anchors: Record<string, { zh: string; en: string }>;
  };
  formula: { role: string; overall: string };
  gate: Record<string, string>;
  roles: Record<"tech" | "ux" | "biz", RubricDimension[]>;
}

export const RUBRIC = rubricDocument as Rubric;

export function dimensionLabel(
  role: "tech" | "ux" | "biz",
  id: string,
): string {
  return RUBRIC.roles[role].find((item) => item.id === id)?.label_zh ?? id;
}
