# Privacy Policy

**Effective date:** 2026-04-21

This Privacy Policy describes how the **iotcli** open-source project ("we", "us", or "our") handles information.

## 1. Overview

iotcli is a local command-line tool for controlling IoT devices. It does not operate any central service, does not collect telemetry, and does not transmit your personal data to project maintainers.

## 2. Information Stored Locally

All data created by iotcli is stored locally on your machine in `~/.iotcli/`:

| File / Directory | Contents |
|------------------|----------|
| `devices.yaml`   | Device names, protocols, IP addresses, and non-sensitive settings |
| `credentials/*.enc` | Fernet-encrypted secrets (tokens, local keys, passwords) |
| `.key`           | Local-only Fernet encryption key (permissions `0600`) |
| `skills/`        | Generated AI-agent skill files based on your device configuration |

No project maintainer, server, or third party (other than the device vendor you are intentionally communicating with) has access to these files.

## 3. Third-Party Services

When you use iotcli to communicate with a device, data is transmitted directly between your machine and the device or its vendor cloud (e.g., Tuya cloud, LG ThinQ). This communication is:

- **Initiated by you** via explicit CLI commands.
- ** Governed by the device vendor's privacy policy**, not this one.

We do not act as an intermediary, proxy, or data processor for these communications.

## 4. No Telemetry or Analytics

iotcli does not:

- Collect usage statistics or crash reports.
- Use tracking cookies or fingerprinting.
- Send data to external analytics services.
- Display advertisements.

## 5. Data Security

- Credentials are encrypted at rest using Fernet (symmetric AES-128 in CBC mode with HMAC).
- The encryption key is stored with owner-only read permissions (`0600`).
- We recommend you keep your operating system and Python environment up to date.

## 6. Open Source

The full source code is available at https://github.com/iotviaai/iotcli. You can inspect exactly what the tool does and how it handles data.

## 7. Changes to This Policy

We may update this policy to reflect changes in the software. The latest version will always be available in the repository.

## 8. Contact

For privacy questions, open an issue at https://github.com/iotviaai/iotcli/issues.
