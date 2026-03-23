/**
 * PKCE (Proof Key for Code Exchange) utilities for OAuth 2.0 authorization code flow.
 * Uses the Web Crypto API for all cryptographic operations.
 */

function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let str = ''
  for (const byte of bytes) {
    str += String.fromCharCode(byte)
  }
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
}

/**
 * Generates a cryptographically random PKCE code verifier (43 chars, base64url-encoded).
 * Uses 32 random bytes → 43-character base64url string (no padding).
 */
export function generateCodeVerifier(): string {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  return base64urlEncode(array.buffer)
}

/**
 * Generates a PKCE code challenge from a code verifier using SHA-256 (S256 method).
 * Returns: BASE64URL(SHA-256(ASCII(code_verifier)))
 */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(verifier)
  const digest = await crypto.subtle.digest('SHA-256', data)
  return base64urlEncode(digest)
}

/**
 * Generates a cryptographically random state token for CSRF protection.
 */
export function generateState(): string {
  const array = new Uint8Array(16)
  crypto.getRandomValues(array)
  return base64urlEncode(array.buffer)
}
