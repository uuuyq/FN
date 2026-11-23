const UNKNOWN_ERROR = "未知异常，请稍后重试。";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: any,
    public requestId?: string,
  ) {
    super(
      typeof detail?.message === "string" && detail.message.trim()
        ? detail.message
        : UNKNOWN_ERROR,
    );
    this.name = "ApiError";
  }
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : UNKNOWN_ERROR;
}
