from decimal import Decimal


def _pdf_text(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_invoice_pdf(order, restaurant_name="NexHaat"):
    lines = [
        restaurant_name,
        "PROFESSIONAL ORDER INVOICE",
        "",
        f"Invoice: {order.order_number}",
        f"Date: {order.created_at:%Y-%m-%d %H:%M}",
        f"Customer: {order.customer_name}",
        f"Email: {order.email or 'N/A'}",
        f"Phone: {order.phone}",
        f"Delivery: {order.address}",
        "",
        "ITEM                                      QTY      PRICE       SUBTOTAL",
        "-" * 76,
    ]
    for item in order.items:
        lines.append(
            f"{item.product_name[:38]:38} {item.quantity:>3}  "
            f"${Decimal(item.price):>8.2f}  ${Decimal(item.subtotal):>10.2f}"
        )
    lines.extend(["", f"TOTAL: ${Decimal(order.total):.2f}", "", "Thank you for ordering with us."])

    commands = ["BT", "/F1 10 Tf", "50 770 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({_pdf_text(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode())
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(pdf)
