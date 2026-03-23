import { describe, it, expect } from 'vitest'
import { generateCodeVerifier, generateCodeChallenge, generateState } from '../utils/pkce'

describe('PKCE utilities', () => {
  it('generateCodeVerifier returns a string of 43-128 characters', () => {
    const verifier = generateCodeVerifier()
    expect(verifier.length).toBeGreaterThanOrEqual(43)
    expect(verifier.length).toBeLessThanOrEqual(128)
  })

  it('generateCodeVerifier uses only base64url-safe characters', () => {
    const verifier = generateCodeVerifier()
    expect(verifier).toMatch(/^[A-Za-z0-9\-_]+$/)
  })

  it('generateCodeVerifier produces a different value on each call', () => {
    const v1 = generateCodeVerifier()
    const v2 = generateCodeVerifier()
    expect(v1).not.toBe(v2)
  })

  it('generateCodeChallenge produces correct SHA-256 base64url hash (RFC 7636 test vector)', async () => {
    // RFC 7636 Appendix B test vector:
    //   code_verifier  = dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
    //   code_challenge = E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
    const challenge = await generateCodeChallenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk') // pragma: allowlist secret
    expect(challenge).toBe('E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM') // pragma: allowlist secret
  })

  it('generateCodeChallenge output contains no base64 padding', async () => {
    const verifier = generateCodeVerifier()
    const challenge = await generateCodeChallenge(verifier)
    expect(challenge).not.toContain('=')
    expect(challenge).not.toContain('+')
    expect(challenge).not.toContain('/')
  })

  it('generateState returns a non-empty base64url string', () => {
    const state = generateState()
    expect(state.length).toBeGreaterThan(0)
    expect(state).toMatch(/^[A-Za-z0-9\-_]+$/)
  })

  it('generateState produces a different value on each call', () => {
    const s1 = generateState()
    const s2 = generateState()
    expect(s1).not.toBe(s2)
  })
})
