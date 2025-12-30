# Guía: Firma de Código para Eliminar SmartScreen

## ¿Qué es SmartScreen y por qué aparece?

**Windows SmartScreen** es una protección de seguridad que muestra advertencias cuando se descarga y ejecuta software de "editor desconocido". Aparece porque:

1. El ejecutable **NO está firmado** digitalmente
2. Windows no reconoce al desarrollador/empresa
3. El archivo es nuevo y no tiene suficiente "reputación"

## ✅ Solución: Certificado de Firma de Código (Code Signing Certificate)

### Opción 1: Certificado EV (Extended Validation) - Recomendado
**Precio**: USD $300-500/año
**Ventaja**: Elimina SmartScreen INMEDIATAMENTE (reputación instantánea)
**Desventaja**: Más caro, requiere validación de identidad empresarial

**Proveedores recomendados**:
- **DigiCert** (más reconocido): https://www.digicert.com/signing/code-signing-certificates
- **Sectigo** (más económico): https://sectigo.com/ssl-certificates-tls/code-signing
- **GlobalSign**: https://www.globalsign.com/en/code-signing-certificate

### Opción 2: Certificado OV (Organization Validation) - Económico
**Precio**: USD $100-200/año
**Ventaja**: Más barato
**Desventaja**: SmartScreen sigue apareciendo hasta acumular "reputación" (varios meses con muchas descargas)

**Proveedores**:
- Mismo que EV, pero pide versión OV

### Opción 3: Certificado Personal (Individual)
**Precio**: USD $80-150/año
**Ventaja**: Más barato, no requiere ser empresa
**Desventaja**: SmartScreen puede seguir apareciendo, menos "confianza"

**Proveedores**:
- **Certum** (acepta individuos): https://www.certum.eu/en/cert_offer_code_signing.xml
- **K Software** (reseller): https://www.ksoftware.net/code-signing-certificates/

---

## 📋 Proceso de Obtención (Ejemplo: DigiCert EV)

### Paso 1: Requisitos para solicitar certificado EV
- **Empresa registrada** (RUT/RFC, registro mercantil)
- **Dominio verificado** (email corporativo, ej: admin@tuempresa.com)
- **Número de teléfono** listado en directorio empresarial
- **Dirección física** de la empresa
- **Documento de identidad** del representante legal

### Paso 2: Compra y validación (7-14 días)
1. Comprar certificado en el sitio del proveedor
2. Enviar documentos de la empresa
3. Esperar llamada de verificación telefónica
4. Recibir USB token físico con el certificado (para EV)

### Paso 3: Firma del ejecutable con SignTool
Una vez que tengas el certificado:

```batch
REM Instalar Windows SDK (incluye signtool.exe)
REM https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/

REM Firmar el ejecutable
signtool sign /f "C:\Certificado\MiCertificado.pfx" ^
              /p "PasswordDelCertificado" ^
              /tr http://timestamp.digicert.com ^
              /td SHA256 ^
              /fd SHA256 ^
              "C:\Path\To\Tu.local.2025.exe"

REM Verificar firma
signtool verify /pa "C:\Path\To\Tu.local.2025.exe"
```

### Paso 4: Firmar también el instalador Setup.exe
```batch
signtool sign /f "C:\Certificado\MiCertificado.pfx" ^
              /p "PasswordDelCertificado" ^
              /tr http://timestamp.digicert.com ^
              /td SHA256 ^
              /fd SHA256 ^
              "installer_output\Tu.local.2025.v2.8.7.Setup.exe"
```

---

## 🤖 Integración con GitHub Actions

Una vez que tengas el certificado, puedes automatizar la firma en el workflow:

```yaml
# .github/workflows/release.yml

- name: Sign executables
  shell: pwsh
  env:
    CERTIFICATE_BASE64: ${{ secrets.CODE_SIGNING_CERT }}
    CERTIFICATE_PASSWORD: ${{ secrets.CERT_PASSWORD }}
  run: |
    # Decodificar certificado desde secret
    $bytes = [Convert]::FromBase64String($env:CERTIFICATE_BASE64)
    [IO.File]::WriteAllBytes("cert.pfx", $bytes)

    # Firmar EXE principal
    & "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe" sign `
      /f cert.pfx `
      /p $env:CERTIFICATE_PASSWORD `
      /tr http://timestamp.digicert.com `
      /td SHA256 `
      /fd SHA256 `
      "dist\Tu local 2025\Tu local 2025.exe"

    # Firmar instalador
    & "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe" sign `
      /f cert.pfx `
      /p $env:CERTIFICATE_PASSWORD `
      /tr http://timestamp.digicert.com `
      /td SHA256 `
      /fd SHA256 `
      "installer_output\Tu.local.2025.v${{ steps.meta.outputs.VER }}.Setup.exe"

    # Limpiar certificado
    Remove-Item cert.pfx -Force
```

---

## 💰 Comparación de Costos Anuales

| Tipo | Precio/año | SmartScreen | Validación | Recomendado para |
|------|-----------|-------------|-----------|------------------|
| **EV** | $300-500 | ✅ Elimina inmediatamente | Empresa + Token USB | **Producción profesional** |
| **OV** | $100-200 | ⚠️ Tarda meses | Empresa | Presupuesto limitado |
| **Individual** | $80-150 | ⚠️ Puede aparecer | DNI/Pasaporte | Desarrolladores individuales |

---

## 🎯 Recomendación Final

Para **Tu local 2025**, considerando que es una aplicación comercial:

1. **Corto plazo** (mientras decides sobre certificado):
   - Publica el hash SHA256 del instalador en tu sitio web
   - Instruye a usuarios a hacer clic derecho → "Más información" → "Ejecutar de todas formas"
   - Proporciona el ZIP sin instalar como alternativa

2. **Largo plazo** (solución definitiva):
   - Invertir en **certificado EV de DigiCert** ($400/año aprox.)
   - Configurar firma automática en GitHub Actions
   - SmartScreen desaparece completamente para todos los usuarios

3. **Alternativa económica**:
   - Certificado OV de Sectigo ($150/año)
   - Esperar 2-3 meses acumulando descargas para ganar reputación
   - SmartScreen eventualmente dejará de aparecer

---

## 📝 Notas Importantes

- **Los certificados expiran**: Debes renovar anualmente
- **Timestamping es crucial**: Permite que el archivo firmado siga siendo válido después de que expire el certificado
- **Firma ANTES de distribuir**: No puedes firmar retroactivamente archivos ya distribuidos
- **Un certificado sirve para múltiples productos**: Puedes firmar todos tus .exe con el mismo certificado

---

## 🔗 Recursos Útiles

- **Microsoft Docs - SignTool**: https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
- **Comparación de proveedores**: https://comodosslstore.com/code-signing
- **Windows SDK Download**: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/
