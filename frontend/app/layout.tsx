export const dynamic = "force-dynamic";
import type { Metadata } from "next";
import "./globals.css";
import {AppShell} from "@/components/app-shell";
import {optionalWorkspaceApi} from "@/lib/workspace";


export const metadata: Metadata = {
  title: "CampusMate 校伴",
  description: "找到可信机会，推进下一步行动",
  icons: { icon: "/favicon.svg" },
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const [health,account,profile]=await Promise.all([optionalWorkspaceApi("/health"),optionalWorkspaceApi("/v1/account"),optionalWorkspaceApi("/v1/profile")]);
  return <html lang="zh-CN"><body><AppShell demo={health?.demo_mode??null} admin={account?.is_admin===true} authenticated={!!account} name={profile?.display_name||"访客"} school={profile?.school||""} agentEnabled={process.env.ENABLE_AGENT_UI==="true"}>{children}</AppShell></body></html>;
}
