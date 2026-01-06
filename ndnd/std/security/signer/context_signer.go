package signer

import (
	enc "github.com/named-data/ndnd/std/encoding"
	"github.com/named-data/ndnd/std/ndn"
)

// ContextSigner is a wrapper around a signer to provide extra context.
type ContextSigner struct {
	ndn.Signer
	KeyLocatorName enc.Name
}

// (AI GENERATED DESCRIPTION): Returns the key locator name stored in the ContextSigner.
func (s *ContextSigner) KeyLocator() enc.Name {
	return s.KeyLocatorName
}
