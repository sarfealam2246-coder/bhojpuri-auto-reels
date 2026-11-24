/// <reference types="vite/client" />

declare module 'tweetnacl-sealedbox-js' {
  export function seal(message: Uint8Array, publicKey: Uint8Array): Uint8Array;
  const sealedbox: {
    seal(message: Uint8Array, publicKey: Uint8Array): Uint8Array;
  };
  export default sealedbox;
}
