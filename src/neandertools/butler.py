"""Butler-backed cutout service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable, Optional, Union

from lsst.daf.butler import Butler
from lsst.geom import Box2I, Point2I

DataId = dict[str, Any]
SkyResolver = Callable[[float, float, Optional[Union[datetime, str]]], Iterable[DataId]]


class ButlerCutoutService:
    """Generate cutouts from an LSST Butler repository."""

    def __init__(self, butler: Any, sky_resolver: Optional[SkyResolver] = None) -> None:
        self._butler = butler
        self._sky_resolver = sky_resolver

    def cutout(
        self,
        ra: Optional[float] = None,
        dec: Optional[float] = None,
        time: Optional[Union[datetime, str]] = None,
        radius: float = 10.0,
        dataset_type: str = "visit_image",
        *,
        visit: Optional[int] = None,
        detector: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[Any]:
        _validate_request(ra=ra, dec=dec, radius=radius, visit=visit, detector=detector)

        if visit is not None:
            image = self._butler.get(dataset_type, dataId={"visit": visit, "detector": detector})
            return [self._extract_cutout(image, radius)]

        assert ra is not None and dec is not None
        if self._sky_resolver is None:
            raise NotImplementedError(
                "Sky-position cutouts require a sky_resolver. "
                "Pass one to cutouts_from_butler(..., sky_resolver=...)."
            )

        data_ids = list(self._sky_resolver(ra, dec, time))
        if limit is not None:
            data_ids = data_ids[:limit]

        images = [self._butler.get(dataset_type, dataId=data_id) for data_id in data_ids]
        return [self._extract_cutout(image, radius) for image in images]

    def _extract_cutout(self, image: Any, radius: float) -> Any:
        if not hasattr(image, "getBBox") or not hasattr(image, "Factory"):
            return image

        bbox = image.getBBox()
        x_center = (bbox.getMinX() + bbox.getMaxX()) // 2
        y_center = (bbox.getMinY() + bbox.getMaxY()) // 2
        r = int(radius)

        cutout_box = Box2I(Point2I(x_center - r, y_center - r), Point2I(x_center + r, y_center + r))
        try:
            cutout_box.clip(bbox)
        except Exception:
            pass

        return image.Factory(image, cutout_box)


def cutouts_from_butler(
    repo: str,
    *,
    collections: Union[str, list[str]],
    butler: Optional[Any] = None,
    sky_resolver: Optional[SkyResolver] = None,
) -> ButlerCutoutService:
    if butler is None:
        butler = Butler(repo, collections=collections)
    return ButlerCutoutService(butler=butler, sky_resolver=sky_resolver)


def _validate_request(
    *,
    ra: Optional[float],
    dec: Optional[float],
    radius: float,
    visit: Optional[int],
    detector: Optional[int],
) -> None:
    if radius <= 0:
        raise ValueError("radius must be > 0")

    visit_mode = visit is not None or detector is not None
    sky_mode = ra is not None or dec is not None

    if visit_mode and sky_mode:
        raise ValueError("Use either (visit, detector) or (ra, dec), not both")

    if visit_mode and (visit is None or detector is None):
        raise ValueError("Both visit and detector must be provided together")

    if not visit_mode and (ra is None or dec is None):
        raise ValueError("Provide either both ra/dec or visit/detector")
