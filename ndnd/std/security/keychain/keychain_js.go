//go:build js && wasm

package keychain

import (
	"crypto/sha256"
	"encoding/hex"
	"syscall/js"

	enc "github.com/named-data/ndnd/std/encoding"
	"github.com/named-data/ndnd/std/log"
	"github.com/named-data/ndnd/std/ndn"
	sig "github.com/named-data/ndnd/std/security/signer"
	jsutil "github.com/named-data/ndnd/std/utils/js"
)

// KeyChainJS is a JS-based keychain.
type KeyChainJS struct {
	mem ndn.KeyChain
	api js.Value
}

// NewKeyChainJS creates a new JS-based keychain.
// See keychain_js.ts for the interface and a sample implementation.
func NewKeyChainJS(api js.Value, pubStore ndn.Store) (ndn.KeyChain, error) {
	kc := &KeyChainJS{
		mem: NewKeyChainMem(pubStore),
		api: api,
	}

	list, err := jsutil.Await(api.Call("list"))
	if err != nil {
		return nil, err
	}

	callback := js.FuncOf(func(this js.Value, args []js.Value) any {
		err := InsertFile(kc.mem, jsutil.JsArrayToSlice(args[0]))
		if err != nil {
			log.Error(kc, "Failed to insert keychain entry", "err", err)
		}

		return nil
	})
	list.Call("forEach", callback)
	callback.Release()

	return kc, nil
}

// (AI GENERATED DESCRIPTION): Returns the string representation of the KeyChainJS instance, which is the literal `"keychain-js"`.
func (kc *KeyChainJS) String() string {
	return "keychain-js"
}

// (AI GENERATED DESCRIPTION): Returns the in-memory store backing the KeyChainJS instance.
func (kc *KeyChainJS) Store() ndn.Store {
	return kc.mem.Store()
}

// (AI GENERATED DESCRIPTION): Retrieves and returns a slice of all key‑chain identities stored in the KeyChainJS memory store.
func (kc *KeyChainJS) Identities() []ndn.KeyChainIdentity {
	return kc.mem.Identities()
}

// (AI GENERATED DESCRIPTION): Returns the KeyChainIdentity with the specified name from the KeyChainJS in‑memory store.
func (kc *KeyChainJS) IdentityByName(name enc.Name) ndn.KeyChainIdentity {
	return kc.mem.IdentityByName(name)
}

// (AI GENERATED DESCRIPTION): Inserts a signer into the in‑memory keychain and persists its secret to a file.
func (kc *KeyChainJS) InsertKey(signer ndn.Signer) error {
	err := kc.mem.InsertKey(signer)
	if err != nil {
		return err
	}

	secret, err := sig.MarshalSecret(signer)
	if err != nil {
		return err
	}

	return kc.writeFile(secret.Join(), EXT_KEY)
}

// (AI GENERATED DESCRIPTION): Inserts the given certificate into the keychain’s in‑memory store and writes it to a file.
func (kc *KeyChainJS) InsertCert(wire []byte) error {
	err := kc.mem.InsertCert(wire)
	if err != nil {
		return err
	}

	return kc.writeFile(wire, EXT_CERT)
}

// (AI GENERATED DESCRIPTION): Writes a binary blob to local storage under a name derived from its SHA‑256 hash, appending the specified extension, via the JavaScript API.
func (kc *KeyChainJS) writeFile(wire []byte, ext string) error {
	hash := sha256.Sum256(wire)
	filename := hex.EncodeToString(hash[:])

	kc.api.Call("write", filename+ext, jsutil.SliceToJsArray(wire))
	return nil
}
