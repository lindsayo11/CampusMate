import { privateApi } from "@/lib/session-api";
import type { Profile } from "@/lib/api";
import { PageHeading } from "@/components/ui";
import { SettingsPanel } from "@/components/settings-panel";

type Account = { user_id: string; email: string | null; is_admin: boolean };
type Section = "personal" | "notifications" | "permissions";

export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ section?: string }> }) {
  const params = await searchParams;
  const section: Section = params.section === "notifications" || params.section === "permissions" ? params.section : "personal";
  const [profile, account] = await Promise.all([
    privateApi("/v1/profile") as Promise<Profile>,
    privateApi("/v1/account") as Promise<Account>,
  ]);

  return (
    <div className="shell settings-shell">
      <PageHeading
        eyebrow="ACCOUNT SETTINGS"
        title="Settings"
        description="Manage your profile, notifications, and workspace permissions."
      />
      <SettingsPanel initialProfile={profile} account={account} initialTab={section} />
    </div>
  );
}
