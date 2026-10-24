class HireHubError(Exception):
    error_code = "HIREHUB_ERROR"
    status_code = 400


class ValidationError(HireHubError):
    error_code = "VALIDATION_ERROR"


class UserAlreadyExistsError(HireHubError):
    error_code = "USER_ALREADY_EXISTS"
    status_code = 409


class InvalidCredentialsError(HireHubError):
    error_code = "INVALID_CREDENTIALS"
    status_code = 401


class UserNotFoundError(HireHubError):
    error_code = "USER_NOT_FOUND"
    status_code = 404


class UnauthorizedError(HireHubError):
    error_code = "UNAUTHORIZED"
    status_code = 403


class JobNotFoundError(HireHubError):
    error_code = "JOB_NOT_FOUND"
    status_code = 404


class JobClosedError(HireHubError):
    error_code = "JOB_CLOSED"
    status_code = 400


class DuplicateApplicationError(HireHubError):
    error_code = "DUPLICATE_APPLICATION"
    status_code = 409


class ApplicationNotFoundError(HireHubError):
    error_code = "APPLICATION_NOT_FOUND"
    status_code = 404


class InterviewNotFoundError(HireHubError):
    error_code = "INTERVIEW_NOT_FOUND"
    status_code = 404


class InvalidApplicationStatusError(HireHubError):
    error_code = "INVALID_APPLICATION_STATUS"
    status_code = 400


class ResumeUploadError(HireHubError):
    error_code = "RESUME_UPLOAD_ERROR"
    status_code = 400
