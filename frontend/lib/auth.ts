// Cognito sign-in (SRP) with amazon-cognito-identity-js: no hosted UI, no client secret.
// The library keeps tokens in localStorage and refreshes the access token when it expires.
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserAttribute,
  CognitoUserPool,
  type CognitoUserSession,
} from "amazon-cognito-identity-js";
import type { AppConfig } from "./config.ts";
import { displayEmail } from "./user.ts";

export class Auth {
  private readonly pool: CognitoUserPool;

  constructor(config: AppConfig) {
    this.pool = new CognitoUserPool({ UserPoolId: config.userPoolId, ClientId: config.clientId });
  }

  private user(email: string): CognitoUser {
    return new CognitoUser({ Username: email.trim().toLowerCase(), Pool: this.pool });
  }

  /** The signed-in user's email (from the ID token; the stored username is the user's sub). */
  currentEmail(session?: CognitoUserSession | null): string | null {
    const username = this.pool.getCurrentUser()?.getUsername() ?? null;
    return displayEmail(session?.getIdToken().decodePayload(), username);
  }

  /** A valid session (refreshed if needed) or null when nobody is signed in. */
  session(): Promise<CognitoUserSession | null> {
    const user = this.pool.getCurrentUser();
    if (!user) return Promise.resolve(null);
    return new Promise((resolve) => {
      user.getSession((err: Error | null, session: CognitoUserSession | null) => {
        resolve(err || !session?.isValid() ? null : session);
      });
    });
  }

  async accessToken(): Promise<string> {
    const session = await this.session();
    if (!session) throw new Error("not signed in");
    return session.getAccessToken().getJwtToken();
  }

  signIn(email: string, password: string): Promise<void> {
    const user = this.user(email);
    const details = new AuthenticationDetails({ Username: email.trim().toLowerCase(), Password: password });
    return new Promise((resolve, reject) => {
      user.authenticateUser(details, {
        onSuccess: () => resolve(),
        onFailure: (err) => reject(friendly(err)),
        newPasswordRequired: () =>
          reject(new Error("This account needs a new password. Ask the admin to reset it.")),
      });
    });
  }

  signUp(email: string, password: string): Promise<void> {
    const attrs = [new CognitoUserAttribute({ Name: "email", Value: email.trim().toLowerCase() })];
    return new Promise((resolve, reject) => {
      this.pool.signUp(email.trim().toLowerCase(), password, attrs, [], (err) =>
        err ? reject(friendly(err)) : resolve(),
      );
    });
  }

  confirm(email: string, code: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.user(email).confirmRegistration(code.trim(), true, (err) =>
        err ? reject(friendly(err)) : resolve(),
      );
    });
  }

  signOut(): void {
    this.pool.getCurrentUser()?.signOut();
  }
}

function friendly(err: unknown): Error {
  const e = err as { code?: string; name?: string; message?: string };
  switch (e.code ?? e.name) {
    case "NotAuthorizedException":
      return new Error("Wrong email or password.");
    case "UserNotConfirmedException":
      return Object.assign(new Error("Confirm your email first: enter the code we sent you."), {
        code: "UserNotConfirmedException",
      });
    case "UsernameExistsException":
      return new Error("An account with this email already exists. Sign in instead.");
    case "InvalidPasswordException":
      return new Error("Password: at least 12 characters with upper case, lower case and a number.");
    case "CodeMismatchException":
    case "ExpiredCodeException":
      return new Error("The code is wrong or expired.");
    default:
      return new Error(e.message || "Something went wrong. Please try again.");
  }
}
