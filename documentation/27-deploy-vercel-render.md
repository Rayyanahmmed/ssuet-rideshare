# 27 · Free production deployment (step by step)

This guide puts the whole project online for **₨ 0 / $0**, using only free tiers that do
not expire and do not need a credit card:

| Part | Service | Free URL / limit |
|---|---|---|
| Backend API | **Render** (free web service, Docker) | `https://<name>.onrender.com` — sleeps after 15 min idle |
| Database | **Neon** (free Postgres) | 1 GB per project, no time limit, sleeps after 5 min idle |
| Web app (students) | **Vercel** (Hobby) | `https://<name>.vercel.app` |
| Admin dashboard | **Vercel** (Hobby) | `https://<name>-admin.vercel.app` |
| Android APK | **Expo EAS** (free build) | download link shown in Admin → App download |
| Keep-awake pinger | **UptimeRobot** (free) | pings the API every 5 min |

Uploaded photos and documents are stored **inside the Neon database** (column `blob`), not on
disk. Free hosts have no persistent disk, so this is the only way they survive restarts.

Nothing in this guide needs a custom domain. You can add one later.

---

## Before you start

You need:

1. A **GitHub** account (Render and Vercel both deploy from a GitHub repository).
2. The project pushed to a **GitHub repository** (public or private).
   - Make sure `mobile/.env` and `admin-dashboard/.env*` are **not** pushed. They are
     gitignored. This matters: a `.env` file in the repo **overrides** the values you type
     into Vercel, and it would point the apps at your laptop.
3. An **Expo** account (free) at <https://expo.dev> for the APK build.
4. Your **admin email and a strong password** for the first administrator account.

Generate nothing by hand: Render generates the JWT secret for you.

---

## Step 0 — Put the project on GitHub

Render and Vercel deploy from a GitHub repository, not from a zip file. You need Git
installed (<https://git-scm.com>).

1. Unzip `SSUET-RideShare-v1.0.0.zip` into a normal folder, e.g. `Documents/SSUET-RideShare`.
2. On GitHub: **+ → New repository** → name `ssuet-rideshare` → choose **Private** → **do not**
   tick "Add a README" or any .gitignore/license (the project already has them). Click
   **Create repository** and copy its address (e.g. `https://github.com/<you>/ssuet-rideshare.git`).
3. Open a terminal **inside the unzipped folder** and run:

   ```bash
   git init -b main
   git add .
   git commit -m "SSUET RideShare v1.0.0"
   git remote add origin https://github.com/<you>/ssuet-rideshare.git
   git push -u origin main
   ```

   GitHub asks you to sign in the first time (use a personal access token as the password
   if it asks for one).

4. Check on GitHub that **no `.env` file** was uploaded (`mobile/.env` and `admin-dashboard/.env`
   must be absent). The `.gitignore` already blocks them; the zip also leaves them out. The
   `.env.example` files are fine and should be there.

Every later change goes the same way: `git add .` → `git commit -m "..."` → `git push`.

---

## Step 1 — Create the database on Neon

1. Go to <https://neon.tech> → **Sign up** (GitHub login is quickest).
2. **Create project**:
   - Name: `ssuet-rideshare`
   - Postgres version: default (16 or newer)
   - Region: the one closest to Pakistan that is offered (e.g. Singapore / AWS ap-southeast-1)
3. On the project dashboard click **Connect** (or **Connection details**).
4. Copy the **connection string**. It looks like this:

   ```
   postgresql://neondb_owner:AbC123xyz@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

5. Use the string **exactly as Neon shows it**, including `?sslmode=require`. The API
   accepts both `postgresql://` and `postgresql+psycopg://`, so you do not need to edit the
   start. Keep this string private. You will paste it into Render in Step 2.

   If Render later logs `channel_binding` errors, delete `&channel_binding=require` from the end.

No tables need to be created by hand. The API runs its migrations on every deploy.

---

## Step 2 — Deploy the API on Render

1. Go to <https://render.com> → sign up with GitHub.
2. Click **New → Blueprint**.
3. Choose your GitHub repository. Render reads `render.yaml` at the repo root and shows one
   service: `ssuet-rideshare-api` (plan **Free**).
4. Render asks you to fill the values marked as required. Fill them like this:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the Neon string from Step 1 (as Neon shows it, with `?sslmode=require`) |
   | `ADMIN_EMAIL` | your admin email, e.g. `transport@ssuet.edu.pk` |
   | `ADMIN_PASSWORD` | a strong password (12+ characters, mixed) |
   | `CORS_ORIGINS` | `https://placeholder.vercel.app` for now; you fix it in Step 5 |
   | `ADMIN_WEB_URL` | `https://placeholder-admin.vercel.app` for now; you fix it in Step 5 |
   | `SMTP_HOST` | `smtp-relay.brevo.com` (see **Email setup** below) |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | your Brevo SMTP login (see **Email setup** below) |
   | `SMTP_PASSWORD` | your Brevo SMTP key (see **Email setup** below) |
   | `EMAIL_FROM` | `SSUET RideShare <the sender email you verified in Brevo>` |

   If you skip email for now, leave the `SMTP_*` values empty. Verification and reset emails
   are then written to the Render logs instead of being sent. Students can still sign in, and
   the admin can issue a reset code (see **Password reset without email** below).

   Leave `JWT_SECRET_KEY` alone. Render generates it.

5. Click **Apply** / **Deploy**. The first build takes 5–10 minutes.
6. When the status is **Live**, open the service page and copy its URL, e.g.
   `https://ssuet-rideshare-api.onrender.com`.
7. Check it works. Open this in a browser:

   ```
   https://ssuet-rideshare-api.onrender.com/api/v1/health
   ```

   You should see a short JSON reply with `"status": "ok"` (or similar). The first call after
   a long idle takes 30–60 seconds. This is normal on the free plan.

**If the deploy fails**, open **Logs** on the service page:

- `could not connect to server` / `SSL` → the `DATABASE_URL` is wrong. Check that
  `?sslmode=require` is at the end and the password was copied completely.
- `password authentication failed` → copy the connection string again from Neon (reset the
  password there if needed).

Your **API base URL** is therefore: `https://ssuet-rideshare-api.onrender.com/api/v1`
(your host + `/api/v1`). Keep it; you need it in Steps 3, 4 and 6.

---

### Email setup (Brevo, free)

Emails send sign-up verification and password reset links. Brevo's free plan allows 300 emails
a day, needs no credit card and no domain. Its emails carry a small "Sent with Brevo" footer.

1. Go to <https://www.brevo.com> → sign up with your email and confirm it.
2. Brevo may ask you to complete your profile and wait for account approval. This can take a
   few hours. Until then, use the **Password reset without email** fallback below.
3. **Senders & IP** (or **Senders**) → **Add a sender**. Use an email address you can read
   (e.g. your Gmail or `transport@ssuet.edu.pk`). Brevo sends a confirmation link to it. Click it.
4. Open **SMTP & API** → **SMTP** tab:
   - **Login** is shown there. Copy it → `SMTP_USER`.
   - Click **Generate a new SMTP key**, copy it once → `SMTP_PASSWORD`.
   - Host `smtp-relay.brevo.com`, port `587` → `SMTP_HOST` and `SMTP_PORT`.
5. In Render → `ssuet-rideshare-api` → **Environment**, set `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS=true` and
   `EMAIL_FROM=SSUET RideShare <the sender from step 3>`. Save. Render redeploys.
6. Test: sign up with a new account. The verification email should arrive within a minute.

If the email does not arrive, check the spam folder and the Brevo **Statistics → Logs** page.

### Password reset without email (admin fallback)

Use this when email is not set up, or when a member cannot receive email.

1. Admin dashboard → **Users** → open the member → **Password reset (when email is not set up)**.
2. Click **Create reset code**. Copy the code. It is valid for 30 minutes and works once.
3. Send the code to the member privately (WhatsApp or in person). Do not post it publicly.
4. The member opens the app → **Forgot password?** → **Already have a reset code?** → pastes
   the code, enters a new password, and taps **Change password**.

Using the code signs the member out of every device. The member's old password stops working.
Accounts that are suspended must be reactivated before a code can be created.

---

## Step 3 — Deploy the admin dashboard on Vercel

1. Go to <https://vercel.com> → sign up with GitHub.
2. **Add New… → Project** → import your repository.
3. Settings on the import screen:
   - **Project name**: `ssuet-rideshare-admin` (this gives `ssuet-rideshare-admin.vercel.app`)
   - **Framework Preset**: Vite (it is also set in `admin-dashboard/vercel.json`)
   - **Root Directory**: click **Edit** and choose `admin-dashboard`
4. Open **Environment Variables** and add:

   | Name | Value |
   |---|---|
   | `VITE_API_BASE_URL` | `https://ssuet-rideshare-api.onrender.com/api/v1` |

   **This variable is required.** Without it the admin calls `/api/v1` on its own Vercel
   address, which does not exist, and sign-in fails.

5. Click **Deploy**. It takes 1–2 minutes.
6. Open the admin URL Vercel gives you (e.g. `https://ssuet-rideshare-admin.vercel.app`).
   Sign in with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from Step 2.

Note the admin's address. You need it in Step 5.

---

## Step 4 — Deploy the web app on Vercel

1. Vercel → **Add New… → Project** → import the **same** repository again.
2. Settings:
   - **Project name**: `ssuet-rideshare-web` (gives `ssuet-rideshare-web.vercel.app`)
   - **Framework Preset**: Other (it is also set in `mobile/vercel.json`)
   - **Root Directory**: `mobile`
3. **Environment Variables**:

   | Name | Value |
   |---|---|
   | `EXPO_PUBLIC_API_URL` | `https://ssuet-rideshare-api.onrender.com/api/v1` |
   | `EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE` | `0` |

   `0` is important. It hides the developer "change server" box from real users.

4. Click **Deploy** and wait 3–5 minutes (Expo builds the web bundle).
5. Open the web URL (e.g. `https://ssuet-rideshare-web.vercel.app`). You should see the
   welcome screen.

Note the web app's address. You need it in Step 5.

---

## Step 5 — Tell the API which websites may call it

Browsers block requests from one website to another unless the API allows it. Now that you
know both Vercel addresses, put them into Render.

1. Render → `ssuet-rideshare-api` → **Environment**.
2. Edit these two values (no spaces, no trailing `/`):

   | Key | Value |
   |---|---|
   | `CORS_ORIGINS` | `https://ssuet-rideshare-web.vercel.app,https://ssuet-rideshare-admin.vercel.app` |
   | `ADMIN_WEB_URL` | `https://ssuet-rideshare-admin.vercel.app` |

3. Save. Render redeploys automatically (2–3 minutes).

Set `ADMIN_BOOTSTRAP_ENABLED` to `false` after your first successful admin sign-in. The
admin is created once; leaving it `true` is harmless but unnecessary.

---

## Step 6 — Build the Android APK (EAS)

The APK is built by Expo in the cloud, so you do not need Android Studio.

1. Check the API address in the APK profile. Open `mobile/eas.json` and find the `apk`
   profile. It already contains this address:

   ```json
   "apk": {
     "distribution": "internal",
     "android": { "buildType": "apk" },
     "env": {
       "APP_VARIANT": "production",
       "EXPO_PUBLIC_API_URL": "https://ssuet-rideshare-api.onrender.com/api/v1",
       "EXPO_PUBLIC_ALLOW_SERVER_OVERRIDE": "0"
     }
   }
   ```

   If Render gave your API a different host in Step 2 (Render adds a suffix when a name is
   taken, e.g. `ssuet-rideshare-api-x7k2.onrender.com`), change that one URL to the host Render
   shows. Then commit and push: `git add . && git commit -m "API address" && git push`.

   The `apk` profile has `autoIncrement: true`, so every new build gets a higher Android
   version code. An update therefore installs over the old APK.

2. On your computer (Node.js 20+ installed):

   ```bash
   cd mobile
   npm install
   npx eas-cli@latest login          # sign in with your Expo account
   npx eas-cli@latest build -p android --profile apk
   ```

   The first time, EAS asks to create an Android keystore. Answer **yes**; EAS keeps it.
   Reuse the same keystore for every build. Android only installs an update over an old APK
   when both are signed with the same key.

3. Wait 10–20 minutes. When it finishes, EAS prints a link like
   `https://expo.dev/artifacts/eas/xxxxxxxx.apk`. Open it on a phone to test the download.

4. **Copy that APK link.** You will paste it into the admin dashboard in Step 7.

**To publish an update later:** change the code, push, run the same `eas build` command.
EAS raises the build number automatically (`autoIncrement` is on for the `apk` profile).
Then paste the new link in Admin → App download.

---

## Step 7 — Publish the APK download link

1. Open the **admin dashboard** → **App download** (sidebar).
2. Paste the APK link from Step 6 and enter a version, e.g. `1.0.0`.
3. Save.
4. Open the **web app** → the welcome screen shows an **Download Android app** button. Click
   it on your computer or phone to confirm the APK downloads.

To take the button down, clear the link and save. No redeploy is needed.

---

## Step 8 — Keep the API awake (free tier)

Render's free plan stops a service after 15 minutes without traffic. The next visitor then
waits about a minute. To avoid that, ping the API every 5 minutes:

1. Sign up at <https://uptimerobot.com> (free).
2. **+ New monitor** → type **HTTP(s)** → URL:
   `https://ssuet-rideshare-api.onrender.com/api/v1/health` → interval **5 minutes**.
3. Save.

Render's free plan gives 750 hours a month. A service that never sleeps uses about 744 of
them, so the monitor keeps the API awake within the limit. Do not add a second service to
the same account.

---

## Step 9 — Final test (do this on the live URLs)

| Check | How | Expected |
|---|---|---|
| API alive | open `/api/v1/health` | JSON reply |
| Admin sign-in | admin URL, admin email + password | dashboard opens, no CORS error in the browser console (F12) |
| Student sign-up | web app → sign up with an `@ssuet.edu.pk` email | verification email arrives (if Brevo is set up); otherwise it appears in Render logs |
| Password reset | admin → member → **Create reset code**, then in the app **Forgot password? → Already have a reset code?** | password changes and the new password signs in |
| Map | admin → **Map API** | shows the OpenStreetMap provider, no key needed |
| Photo upload | student profile → add a photo | photo appears after upload and after a page refresh |
| APK button | web app welcome screen | downloads the APK |
| Install APK | open the APK on an Android phone | installs (allow "Install unknown apps" for the browser when asked) |
| Navigation | open a screen, press back | goes back to the previous screen |

If a page says "Failed to fetch" or shows a CORS error in the console, go back to Step 5 and
check the spelling of the Vercel addresses in `CORS_ORIGINS`. Then redeploy Render.

---

## Updating the site later

- **Code change:** push to GitHub. Render and both Vercel projects redeploy automatically.
- **Changed `EXPO_PUBLIC_API_URL` or `VITE_API_BASE_URL`:** these are baked in at build time.
  Change the value in Vercel, then **Deployments → ⋯ → Redeploy** (uncheck "use cache").
- **New APK:** build with EAS (Step 6), then paste the new link in Admin → App download.
- **Map API key rotation:** Admin → **Map API**. No redeploy, no code change.

---

## Notes and limits (free tier)

- **Cold start:** with UptimeRobot the API stays awake. Without it, the first request after
  15 idle minutes takes about 1 minute.
- **Database sleep:** Neon sleeps after 5 idle minutes and wakes on the next query (about a
  second). Fine for this project.
- **Storage:** Neon gives 1 GB per project. Profile photos are resized to 512 px WebP, so
  this is plenty for a student app. Monitor usage in the Neon dashboard.
- **Uploads limit:** `MAX_UPLOAD_BYTES` is 5 MB per file (Render environment).
- **Email:** set up Brevo (see **Email setup**) for verification and reset emails. Until then
  the emails are written to the Render logs, and the admin reset code covers password resets.
- **Brevo limit:** 300 emails a day on the free plan. Sign-up and reset emails are well within
  that for this project.
- **Backups:** Neon keeps point-in-time history for a short window on the free plan. Export a
  dump occasionally (`pg_dump` with the connection string) for anything you cannot lose.
- **Database URL:** if you ever rotate the Neon password, update `DATABASE_URL` on Render and
  redeploy.
- **Map:** the map provider and its key are changed only in Admin → Map API. No redeploy.
- **Deploy from GitHub, not from a zip** (see Step 0). A `mobile/.env` with local addresses
  overrides the Vercel values. Keep `.env` files out of the repository.

---

## Quick reference

| Thing | Where |
|---|---|
| API base | `https://ssuet-rideshare-api.onrender.com/api/v1` |
| Admin | `https://ssuet-rideshare-admin.vercel.app` |
| Web app | `https://ssuet-rideshare-web.vercel.app` |
| Database | Neon dashboard → Connection details |
| APK link | Admin → App download |
| Logs | Render → service → Logs |
