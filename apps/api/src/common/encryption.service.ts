import { createCipheriv, createDecipheriv, createHash, randomBytes } from "crypto";
import { Injectable } from "@nestjs/common";

@Injectable()
export class EncryptionService {
  private readonly algorithm = "aes-256-gcm";
  private readonly key: Buffer;

  constructor() {
    const raw = process.env.ENCRYPTION_KEY || "0123456789abcdef0123456789abcdef";
    this.key = createHash("sha256").update(raw).digest();
  }

  encrypt(plainText: string): string {
    const iv = randomBytes(12);
    const cipher = createCipheriv(this.algorithm, this.key, iv);
    const encrypted = Buffer.concat([cipher.update(plainText, "utf8"), cipher.final()]);
    const authTag = cipher.getAuthTag();
    return `${iv.toString("hex")}:${authTag.toString("hex")}:${encrypted.toString("hex")}`;
  }

  decrypt(payload: string): string {
    const [ivHex, tagHex, encryptedHex] = payload.split(":");
    const decipher = createDecipheriv(this.algorithm, this.key, Buffer.from(ivHex, "hex"));
    decipher.setAuthTag(Buffer.from(tagHex, "hex"));
    const decrypted = Buffer.concat([decipher.update(Buffer.from(encryptedHex, "hex")), decipher.final()]);
    return decrypted.toString("utf8");
  }
}
