import qrcode
import uuid
from pathlib import Path
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import CircleModuleDrawer

class QR:
    def __init__(self, data: str, box_size: int = 10):
        self.data = data
        self.box_size = box_size
        self._path = None

    def __enter__(self):
        random_name = uuid.uuid4().hex[:8]
        self._path = Path(f"{random_name}.png")
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=self.box_size,
            border=4,
        )
        qr.add_data(self.data)
        qr.make(fit=True)
        
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=CircleModuleDrawer(),
            fill_color="black",
            back_color="white"
        )
        img.save(self._path, "PNG")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._path and self._path.exists():
            self._path.unlink()

    def get(self) -> str:
        return str(self._path)

