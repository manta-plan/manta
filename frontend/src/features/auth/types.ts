export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
};

export type LoginResponse = TokenResponse;

export type RefreshResponse = TokenResponse;
