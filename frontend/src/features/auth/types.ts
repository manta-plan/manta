export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
};

export type LoginResponse = TokenResponse;

export type RefreshResponse = TokenResponse;

export type RegisterResponse = {
  uuid: string;
  username: string;
  idp_subject: string;
  idp_source: string;
  created_at: string;
};
