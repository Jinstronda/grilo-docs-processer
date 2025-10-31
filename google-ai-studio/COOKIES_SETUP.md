# Cookie Setup for Auto-Login

To enable automatic login to Google AI Studio, you need to save your browser cookies.

## How to Get Your Cookies

### Method 1: Using Browser Extension (Recommended)

1. Install a cookie export extension (e.g., "EditThisCookie" or "Cookie-Editor")
2. Sign in to https://aistudio.google.com/ in your browser
3. Click the extension icon
4. Export all cookies as JSON
5. Save to `google-ai-studio/cookies.json`

### Method 2: Using Browser DevTools

1. Sign in to https://aistudio.google.com/
2. Press F12 to open DevTools
3. Go to Application tab → Cookies → https://aistudio.google.com
4. Manually copy relevant cookies (especially `SID`, `__Secure-*PSID*` cookies)
5. Format as JSON array and save to `google-ai-studio/cookies.json`

## Cookie Format

See `cookies.example.json` for the required format:

```json
[
  {
    "name": "SID",
    "value": "your_session_value",
    "domain": ".google.com",
    "path": "/",
    "expires": 1796387033,
    "httpOnly": false,
    "secure": false,
    "sameSite": "Lax"
  }
]
```

## Important Cookies for Google Authentication

The most critical cookies are:
- `SID` - Session ID
- `__Secure-1PSID` - Secure session ID
- `__Secure-3PSID` - Another secure session
- `APISID` - API session ID
- `SAPISID` - Secure API session ID

## Security Notes

⚠️ **IMPORTANT:** 
- `cookies.json` is in `.gitignore` and will NOT be committed to git
- These cookies give access to your Google account
- Never share your `cookies.json` file
- Cookies expire - you'll need to update them periodically

## How the Script Uses Cookies

When you run `interactive_extractor.py`:

1. Script checks if `cookies.json` exists
2. If found, loads cookies into the browser context
3. Navigates to Google AI Studio
4. You should be automatically logged in!
5. If cookies expired, you'll be asked to sign in manually

## Refreshing Cookies

If cookies expire (usually after a few weeks):

1. Sign in to Google AI Studio manually
2. Export fresh cookies
3. Replace `cookies.json` with new cookies
4. Run the script again

## Alternative: No Cookies

If you don't want to use cookies:

- Simply don't create `cookies.json`
- The script will ask you to sign in manually each time
- Still saves time on the extraction automation

