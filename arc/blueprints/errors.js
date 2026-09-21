'use strict';
// Explicit HTTP failures for task-defined validation and authorization rules.
// The shared server converts status/message to {error: message} and hides 5xx details.
class HttpError extends Error {
  constructor(status, message) {
    if (!Number.isInteger(status) || status < 400 || status > 499) {
      throw new RangeError('HttpError status must be 400..499');
    }
    if (typeof message !== 'string' || !message.trim()) {
      throw new TypeError('HttpError message must be a nonempty string');
    }
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

module.exports = {HttpError};
