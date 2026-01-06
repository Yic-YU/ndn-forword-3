package keychain

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	enc "github.com/named-data/ndnd/std/encoding"
	"github.com/named-data/ndnd/std/log"
	"github.com/named-data/ndnd/std/ndn"
	sec "github.com/named-data/ndnd/std/security"
	sig "github.com/named-data/ndnd/std/security/signer"
)

const EXT_KEY = ".key"
const EXT_CERT = ".cert"
const EXT_PEM = ".pem"

// KeyChainDir is a directory-based keychain.
type KeyChainDir struct {
	mem  ndn.KeyChain
	path string
}

// NewKeyChainDir creates a new in-memory keychain.
func NewKeyChainDir(path string, pubStore ndn.Store) (ndn.KeyChain, error) {
	kc := &KeyChainDir{
		mem:  NewKeyChainMem(pubStore),
		path: path,
	}

	// Create directory if it doesn't exist
	err := os.MkdirAll(path, 0700)
	if err != nil {
		return nil, err
	}

	// Populate keychain from disk
	entries, err := os.ReadDir(path)
	if err != nil {
		return nil, err
	}
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), EXT_KEY) &&
			!strings.HasSuffix(entry.Name(), EXT_CERT) &&
			!strings.HasSuffix(entry.Name(), EXT_PEM) {
			continue
		}

		if entry.IsDir() {
			continue
		}

		filename := filepath.Join(path, entry.Name())
		content, err := os.ReadFile(filename)
		if err != nil {
			log.Warn(kc, "Failed to read keychain entry", "file", filename, "err", err)
			continue
		}

		err = InsertFile(kc.mem, content)
		if err != nil {
			log.Error(kc, "Failed to insert keychain entries", "file", filename, "err", err)
		}
	}

	return kc, nil
}

// (AI GENERATED DESCRIPTION): Returns a string representation of the KeyChainDir, displaying the path to the keychain directory.
func (kc *KeyChainDir) String() string {
	return fmt.Sprintf("keychain-dir (%s)", kc.path)
}

// (AI GENERATED DESCRIPTION): Returns the underlying in‑memory store that backs the KeyChainDir.
func (kc *KeyChainDir) Store() ndn.Store {
	return kc.mem.Store()
}

// (AI GENERATED DESCRIPTION): Returns a slice of all identities currently stored in the key‑chain directory.
func (kc *KeyChainDir) Identities() []ndn.KeyChainIdentity {
	return kc.mem.Identities()
}

// (AI GENERATED DESCRIPTION): Retrieves and returns the identity that matches the specified name from the keychain directory’s in‑memory store.
func (kc *KeyChainDir) IdentityByName(name enc.Name) ndn.KeyChainIdentity {
	return kc.mem.IdentityByName(name)
}

// (AI GENERATED DESCRIPTION): Adds a signer to the in‑memory key chain and writes its secret key to disk in a file with the key extension.
func (kc *KeyChainDir) InsertKey(signer ndn.Signer) error {
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

// (AI GENERATED DESCRIPTION): Inserts the given certificate (in wire format) into the in‑memory key chain and writes it to disk with the certificate file extension.
func (kc *KeyChainDir) InsertCert(wire []byte) error {
	err := kc.mem.InsertCert(wire)
	if err != nil {
		return err
	}

	return kc.writeFile(wire, EXT_CERT)
}

// (AI GENERATED DESCRIPTION): Writes the given binary data to a PEM‑encoded file named after its SHA‑256 hash (plus the supplied extension) in the keychain directory, with permissions set to 0600.
func (kc *KeyChainDir) writeFile(wire []byte, ext string) error {
	hash := sha256.Sum256(wire)
	filename := hex.EncodeToString(hash[:])
	path := filepath.Join(kc.path, filename+ext)

	str, err := sec.PemEncode(wire)
	if err != nil {
		return err
	}

	return os.WriteFile(path, str, 0600)
}
