(function () {
  // The four-page auth site may be served from a different port or host than
  // the CampusMate console. OAuth and session calls must always use the
  // configured console origin, not the current auth page origin.
  const CONSOLE_URL = window.CAMPUSMATE_CONSOLE_URL || "https://campus-mate.shuziyuxingxing.dpdns.org";
  const message = (text) => { const node = document.querySelector("[role=status]"); if (node) node.textContent = text; };
  const request = async (payload) => {
    let response;
    try {
      response = await fetch(CONSOLE_URL + "/api/session", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      throw new Error("暂时无法连接登录服务，请检查网络或稍后重试。");
    }
    let data = {};
    try { data = await response.json(); } catch { throw new Error("登录服务响应异常，请重试。"); }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "认证失败，请重试。");
    return data;
  };

  document.querySelectorAll("[data-google-login]").forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault();
    window.location.href = CONSOLE_URL + "/api/session/oauth?next=%2Fconsole";
  }));

  document.querySelectorAll("[data-session-form]").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (submitter instanceof HTMLButtonElement) submitter.disabled = true;
    const email = form.querySelector("[name=email]")?.value.trim();
    const password = form.querySelector("[name=password]")?.value || "";
    const confirmation = form.querySelector("[name=password_confirmation]")?.value || "";
    const token = form.querySelector("[name=token]")?.value.trim() || "";
    const stage = form.dataset.stage || "email";
    let action = form.dataset.action || "login";
    if (action === "signup") action = stage === "email" ? "send_code" : stage === "otp" ? "verify_signup" : "set_signup_password";
    if (action === "verify_signup" && !/^\d{8}$/.test(token)) return message("请输入邮箱收到的 8 位数字验证码。");
    if (action === "set_signup_password" && (password.length < 8 || password !== confirmation)) return message("两次密码须一致，且至少包含 8 个字符。");
    message(action === "signup" ? "正在发送验证码…" : action === "verify_signup" ? "正在验证邮箱…" : action === "set_signup_password" ? "正在创建账号…" : "正在登录…");
    try {
    const payload = action === "verify_signup" ? { email, token, action } : { email, ...(password ? { password } : {}), action };
      const data = await request(payload);
      if (action === "send_code") {
        if (data.otp_required !== true) throw new Error("验证码状态未确认，请重试。");
        form.dataset.stage = "otp";
        form.querySelector("[data-email-stage]")?.setAttribute("hidden", "true");
        const otp = form.querySelector("[data-otp-fields]"); if (otp) otp.hidden = false;
        const tokenInput = form.querySelector("[name=token]"); if (tokenInput) { tokenInput.disabled = false; tokenInput.focus(); }
        form.querySelector("[data-verify-submit]")?.removeAttribute("disabled");
        form.querySelector("[data-resend-code]")?.removeAttribute("disabled");
        return message("发送请求已受理，请检查收件箱和垃圾邮件；如未收到，可在 5 分钟后重试。");
      }
      if (action === "verify_signup") {
        form.dataset.stage = "password";
        form.querySelector("[data-otp-fields]")?.setAttribute("hidden", "true");
        const verifiedToken = form.querySelector("[name=token]"); if (verifiedToken) verifiedToken.disabled = true;
        form.querySelector("[data-verify-submit]")?.setAttribute("disabled", "true");
        form.querySelector("[data-resend-code]")?.setAttribute("disabled", "true");
        const fields = form.querySelector("[data-password-fields]"); if (fields) fields.hidden = false;
        form.querySelectorAll("[data-password-fields] input").forEach((input) => { input.disabled = false; });
        form.querySelector("[data-password-fields] input[name=password]")?.focus();
        return message("邮箱验证成功，请设置密码完成注册。");
      }
      window.location.href = `${CONSOLE_URL}/console`;
    } catch (error) { message(error instanceof Error ? error.message : "认证失败，请稍后重试。"); }
    finally {
      if (submitter instanceof HTMLButtonElement && !["otp", "password"].includes(form.dataset.stage || "")) submitter.disabled = false;
    }
  }));

  document.querySelectorAll("[data-resend-code]").forEach((button) => button.addEventListener("click", async () => {
    const form = button.closest("[data-session-form]"); const email = form?.querySelector("[name=email]")?.value.trim();
    if (!email) return message("请先填写邮箱地址。");
    button.disabled = true;
    try {
      const data = await request({ email, action: "resend_signup" });
      message(data.message || "发送请求已受理，请检查收件箱与垃圾邮件。");
      let remaining = 30;
      const originalLabel = button.textContent || "重新发送";
      button.textContent = `${originalLabel}（${remaining} 秒）`;
      const timer = window.setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          window.clearInterval(timer);
          button.disabled = false;
          button.textContent = originalLabel;
        } else button.textContent = `${originalLabel}（${remaining} 秒）`;
      }, 1000);
    } catch (error) { message(error instanceof Error ? error.message : "验证码重发失败，请稍后重试。"); button.disabled = false; }
  }));

  const oauthError = new URLSearchParams(window.location.search).get("oauth_error");
  if (oauthError) message("Google 登录未完成（" + oauthError + "），请重试。");
})();

