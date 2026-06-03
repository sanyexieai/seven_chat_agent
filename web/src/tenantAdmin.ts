export type TenantRole = "admin" | "member";

export function isTenantAdmin(role: string | undefined | null): boolean {
  return role === "admin";
}

export function tenantRoleLabel(role: string): string {
  return role === "admin" ? "管理员" : "成员";
}
