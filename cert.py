import pathlib
from OpenSSL import crypto

p = pathlib.Path("certs")
p.mkdir(exist_ok=True)

key = crypto.PKey()
key.generate_key(crypto.TYPE_RSA, 2048)
cert = crypto.X509()
cert.get_subject().CN = "localhost"
cert.set_serial_number(1)
cert.gmtime_adj_notBefore(0)
cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # 1 year
cert.set_issuer(cert.get_subject())
cert.set_pubkey(key)
cert.sign(key, "sha256")

(p / "cert.pem").write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
(p / "key.pem").write_bytes(crypto.dump_privatekey(crypto.FILETYPE_PEM, key))
print("Wrote certs/cert.pem and certs/key.pem")
