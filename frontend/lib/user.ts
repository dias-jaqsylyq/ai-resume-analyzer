// What the header shows for the signed-in user. With email as the Cognito sign-in alias, the
// stored username is the user's sub (a UUID), so the email comes from the ID token instead.

export function displayEmail(idTokenPayload: Record<string, unknown> | undefined, username: string | null): string | null {
  const email = idTokenPayload?.email;
  if (typeof email === "string" && email.includes("@")) return email;
  return username;
}
