export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
};

export type RegisterResponse = {
  uuid: string;
  username: string;
  idp_subject: string;
  idp_source: string;
  created_at: string;
};
