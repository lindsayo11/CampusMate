"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import Link from "next/link";
import { apiBase, type Profile } from "@/lib/api";
import { Icon, streams } from "@/components/ui";
import { ProfileForm } from "@/components/profile-form";
import s from "./settings-studio.module.css";

type Account = { user_id: string; email: string | null; is_admin: boolean };
type Tab = "personal" | "notifications" | "permissions";

type StoredSettings = {
  avatar: string;
  location: string;
  instruction: string;
  notifications: { secretMessage: boolean; qualification: boolean; sourceUpdates: boolean };
  permissions: { messages: boolean; teamStatus: boolean; progress: boolean };
};

const storageKey = "campusmate.settings";
const defaults: StoredSettings = {
  avatar: "",
  location: "广州",
  instruction: "",
  notifications: { secretMessage: true, qualification: true, sourceUpdates: true },
  permissions: { messages: true, teamStatus: false, progress: true },
};

function getStoredSettings(): StoredSettings {
  if (typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<StoredSettings>;
    return {
      ...defaults,
      ...parsed,
      notifications: { ...defaults.notifications, ...parsed.notifications },
      permissions: { ...defaults.permissions, ...parsed.permissions },
    };
  } catch {
    return defaults;
  }
}

function profilePayload(profile: Profile, displayName: string) {
  return {
    display_name: displayName.trim() || profile.display_name,
    discoverable: profile.discoverable,
    school: profile.school,
    college: profile.college,
    grade: profile.grade,
    major: profile.major,
    interests: profile.interests,
    skills: profile.skills,
    weekly_hours: profile.weekly_hours,
    degree: profile.degree,
    target_year: profile.target_year,
    target_path: profile.target_path,
    target_region: profile.target_region,
    language_score: profile.language_score,
    research_exp: profile.research_exp,
    internship_exp: profile.internship_exp,
    competition_exp: profile.competition_exp,
    startup_exp: profile.startup_exp,
  };
}

export function SettingsPanel({ initialProfile, account, initialTab = "personal" }: { initialProfile: Profile; account: Account; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [settings, setSettings] = useState<StoredSettings>(defaults);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState(initialProfile);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setSettings(getStoredSettings());
    void fetch(`${apiBase}/v1/notification-preferences`, { cache: "no-store" })
      .then(async response => {
        if (!response.ok) return;
        const preference = await response.json() as { source_updates?: boolean };
        setSettings(current => {
          const next = { ...current, notifications: { ...current.notifications, sourceUpdates: preference.source_updates !== false } };
          try { window.localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* optional */ }
          return next;
        });
      }).catch(() => {});
  }, []);
  useEffect(() => setTab(initialTab), [initialTab]);

  function persist(next: StoredSettings) {
    setSettings(next);
    try { window.localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* storage is optional */ }
  }

  function updateField<K extends keyof StoredSettings>(key: K, value: StoredSettings[K]) {
    persist({ ...settings, [key]: value });
  }

  function updateToggle(section: "notifications" | "permissions", key: string, value: boolean) {
    const next = { ...settings, [section]: { ...settings[section], [key]: value } } as StoredSettings;
    persist(next);
    if (section === "notifications" && key === "sourceUpdates") {
      setError("");
      void fetch(`${apiBase}/v1/notification-preferences`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_updates: value }),
      }).then(async response => {
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(typeof body.detail === "string" ? body.detail : "通知设置保存失败");
        }
      }).catch(reason => {
        setSettings(current => {
          const restored = { ...current, notifications: { ...current.notifications, sourceUpdates: !value } };
          try { window.localStorage.setItem(storageKey, JSON.stringify(restored)); } catch { /* optional */ }
          return restored;
        });
        setError(reason instanceof Error ? reason.message : "通知设置保存失败");
      });
    }
  }

  function onAvatarChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 2 * 1024 * 1024) {
      setError("请选择不超过 2 MB 的图片。");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        updateField("avatar", reader.result);
        setError("");
      }
    };
    reader.onerror = () => setError("图片读取失败。");
    reader.readAsDataURL(file);
  }

  function downloadProfile() {
    const data = { ...profilePayload(profile, profile.display_name), location: settings.location, instruction: settings.instruction };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = "campusmate-profile.json"; link.click();
    URL.revokeObjectURL(url);
  }

  async function signOut(next = "/login") {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await fetch("/api/session", { method: "DELETE" });
      window.location.href = next;
    } catch {
      setError("退出会话失败，请稍后重试。");
      setBusy(false);
    }
  }

  const email = account.email || "未获取到登录邮箱";
  const tabs: { id: Tab; label: string; icon: "file" | "bell" | "shield" }[] = [
    { id: "personal", label: "个人信息", icon: "file" },
    { id: "notifications", label: "通知", icon: "bell" },
    { id: "permissions", label: "权限", icon: "shield" },
  ];

  const direction = streams.find(item => item.code === profile.target_path)?.name || "探索中";
  return (
    <section className={s.studio} aria-label="设置工作区">
      <header className={s.identity}>
        <div className={s.identityMain}>
          <button className={s.avatar} type="button" onClick={() => fileInput.current?.click()} aria-label="更换头像">
            {settings.avatar ? <img src={settings.avatar} alt="" /> : <img src="/landing/assets/logo.svg" alt="" />}
            <span><Icon name="plus" size={14}/></span>
          </button>
          <div><span className={s.overline}>我的校伴 · 个人档案</span><h1>{profile.display_name || "同学"}<small>的成长空间</small></h1><p>{[profile.school, profile.major].filter(Boolean).join(" / ") || "从完善你的个人信息开始"}</p></div>
        </div>
        <dl className={s.identityFacts}><div><dt>发展方向</dt><dd>{direction}</dd></div><div><dt>目标年份</dt><dd>{profile.target_year || "待确定"}</dd></div></dl>
        <input ref={fileInput} className="sr-only" type="file" accept="image/png,image/jpeg,image/webp" onChange={onAvatarChange} />
      </header>
      <nav className={s.tabs} aria-label="设置栏目">
        {tabs.map((item) => (
          <Link key={item.id} href={`/settings?section=${item.id}`} scroll={false} aria-current={tab === item.id ? "page" : undefined} onClick={() => setTab(item.id)}>
            <Icon name={item.icon} size={16} /> <span>{item.label}</span>
          </Link>
        ))}
        <span className={s.tabHint}>设置，让校伴更懂你</span>
      </nav>

      {tab === "personal" && <div data-motion-key={tab}>
        <div className={s.sectionHeading}><div><h2>把你的下一步，写在这里。</h2><p>学业、目标与经历，共同构成你的个人画像。</p></div><button type="button" onClick={downloadProfile}><Icon name="file" size={15} />下载资料</button></div>
        <ProfileForm initial={profile} onSaved={setProfile} />
        <div className={s.deviceGrid}>
          <section className={s.card}><header><Icon name="users" size={18}/><h2>账号名片</h2></header><dl className={s.accountFacts}><div><dt>登录邮箱</dt><dd>{email}</dd></div><div><dt>账号 ID</dt><dd>{account.user_id}</dd></div></dl><div className={s.smallActions}><button type="button" onClick={() => fileInput.current?.click()}>更换头像</button>{settings.avatar && <button type="button" onClick={() => updateField("avatar", "")}>恢复默认</button>}<small>头像保存在本设备 · 最大 2 MB</small></div></section>
          <section className={s.card}><header><Icon name="file" size={18}/><h2>个人备注</h2><small>保存在本设备</small></header><label>所在城市<input value={settings.location} maxLength={80} placeholder="填写所在城市或地区" onChange={(event) => updateField("location", event.target.value)}/></label><label>写给校伴<textarea rows={2} value={settings.instruction} maxLength={1000} placeholder="你希望校伴如何帮助你？" onChange={(event) => updateField("instruction", event.target.value)}/></label></section>
        </div>
        <footer className={s.accountActions}><span><Icon name="shield" size={16}/>你的账号，由你掌握</span><div><button type="button" onClick={() => void signOut("/login?switch=1")} disabled={busy}><Icon name="users" size={15} />切换账号</button><button className={s.danger} type="button" onClick={() => void signOut()} disabled={busy}><Icon name="logout" size={15} />退出登录</button></div></footer>
      </div>}

      {tab === "notifications" && <div className={s.preferences} data-motion-key={tab}><div className={s.preferenceIntro}><span className={s.largeIcon}><Icon name="bell" size={28}/></span><h2>只留意<br/>重要的消息。</h2><p>让更新跟上你，<br/>不打断你的节奏。</p><Link href="/notifications">前往通知中心 <Icon name="arrow" size={15}/></Link></div><div className={s.options}>{([ ["sourceUpdates", "发展路线信息更新", "关注的原文、机会与截止日期发生变化时提醒。"], ["secretMessage", "私信提醒", "收到站内消息时提醒。"], ["qualification", "资格核对提醒", "资格核对完成后提醒。"] ] as const).map(([key, title, description]) => <label className={s.option} key={key}><span><strong>{title}</strong><small>{description}</small><em>{key === "sourceUpdates" ? "同步至账号" : "本设备偏好"}</em></span><input role="switch" type="checkbox" checked={settings.notifications[key]} onChange={(event) => updateToggle("notifications", key, event.target.checked)} /></label>)}</div></div>}

      {tab === "permissions" && <div className={s.preferences} data-motion-key={tab}><div className={s.preferenceIntro}><span className={s.largeIcon}><Icon name="shield" size={28}/></span><h2>保持连接，<br/>也保留边界。</h2><p>管理本设备的协作偏好。<br/>公开画像开关在个人信息中设置。</p><Link href="/safety">隐私与安全 <Icon name="arrow" size={15}/></Link></div><div className={s.options}>{([ ["messages", "接收工作区消息", "允许队友发起工作区对话。"], ["teamStatus", "展示团队状态", "让队友了解你的协作意愿。"], ["progress", "展示发展进度", "分享所选方向的概览进度。"] ] as const).map(([key, title, description]) => <label className={s.option} key={key}><span><strong>{title}</strong><small>{description}</small><em>本设备偏好</em></span><input role="switch" type="checkbox" checked={settings.permissions[key]} onChange={(event) => updateToggle("permissions", key, event.target.checked)} /></label>)}</div></div>}
      {error && <p className={s.error} role="alert">{error}</p>}
    </section>
  );
}
