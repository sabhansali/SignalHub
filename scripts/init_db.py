from app.database import Base, engine
import app.models  # noqa: F401

Base.metadata.create_all(bind=engine)
print("SignalHub database schema created.")
